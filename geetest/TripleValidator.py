import json
import os.path
import re
import time

import cv2
import loguru
import numpy as np
import onnxruntime
import requests
from PIL import Image
from scipy.optimize import linear_sum_assignment
from scipy.spatial.distance import cdist
from scipy.special import softmax
from geetest.Validator import Validator, test_validator
from util import FILES_ROOT_PATH, bili_ticket_gt_python, EXE_PATH


# https://github.com/Amorter/biliTicker_gt/blob/f378891457bb78bcacf181eaf642b11f5543b4e0/src/click.rs#L166


def letterbox_resize(image, target_size=(384, 384), fill_color=(0, 0, 0)):
    """
    使用左上角对齐方法调整图像大小。
    :param image: 输入的PIL图像
    :param target_size: 目标尺寸 (width, height)
    :param fill_color: 填充颜色，默认为黑色 (0, 0, 0)
    :return: 调整后的PIL图像
    """
    target_width, target_height = target_size
    new_image = Image.new("RGB", (target_width, target_height), fill_color)
    paste_x = 0
    paste_y = 0
    new_image.paste(image, (paste_x, paste_y))

    return new_image


class Model:
    def __init__(self, debugDir=None):
        self.yolo = onnxruntime.InferenceSession(
            os.path.join(FILES_ROOT_PATH, "geetest", "model", "yolo.onnx")
        )
        self.siamese = onnxruntime.InferenceSession(
            os.path.join(FILES_ROOT_PATH, "geetest", "model", "triple.onnx")
        )
        if debugDir:
            os.makedirs(debugDir, exist_ok=True)
        self.debugDir = debugDir
        self.origin_img = None
        self.size = (96, 96)

    def detect(self, img):
        confidence_thres = 0.8
        iou_thres = 0.8
        model_inputs = self.yolo.get_inputs()
        input_shape = model_inputs[0].shape
        input_width = input_shape[2]
        input_height = input_shape[3]
        self.origin_img = cv2.imdecode(
            np.frombuffer(img, np.uint8), cv2.IMREAD_ANYCOLOR
        )
        img = Image.fromarray(self.origin_img)
        img = letterbox_resize(img, (input_height, input_width))
        image_data = np.array(img) / 255.0
        image_data = np.transpose(image_data, (2, 0, 1))
        image_data = np.expand_dims(image_data, axis=0).astype(np.float32)
        output = self.yolo.run(None, {model_inputs[0].name: image_data})
        outputs = np.transpose(np.squeeze(output[0]))
        rows = outputs.shape[0]
        boxes, scores, class_ids = [], [], []
        for i in range(rows):
            classes_scores = outputs[i][4:]
            max_score = np.amax(classes_scores)
            if max_score >= confidence_thres:
                class_id = np.argmax(classes_scores)
                x, y, w, h = outputs[i][0], outputs[i][1], outputs[i][2], outputs[i][3]
                left = int((x - w / 2))
                top = int((y - h / 2))
                width = int(w)
                height = int(h)
                class_ids.append(class_id)
                scores.append(max_score)
                boxes.append([left, top, width, height])
        indices = cv2.dnn.NMSBoxes(boxes, scores, confidence_thres, iou_thres)
        ret_boxes = sorted([boxes[i] for i in indices], key=lambda x: x[0])
        text_imgs = []
        text_boxes = []
        bg_imgs = []
        bg_boxes = []
        for i in ret_boxes:  # type: ignore
            cropped = self.origin_img[i[1] : i[1] + i[3], i[0] : i[0] + i[2]]  # type: ignore
            if cropped.shape[0] < 35 and cropped.shape[1] < 35:
                text_imgs.append(cropped.astype(np.float32))
                text_boxes.append(i)
            else:
                bg_imgs.append(cropped.astype(np.float32))
                bg_boxes.append(i)
        return text_imgs, text_boxes, bg_imgs, bg_boxes

    def match(self, text_imgs, bg_imgs, bg_imgs_box):
        text_imgs = np.stack(
            [
                normalize_image(cv2.resize(img, self.size)).transpose(2, 0, 1)
                for img in text_imgs
            ]
        )  # (n, C, H, W)
        bg_imgs = np.stack(
            [
                normalize_image(cv2.resize(img, self.size)).transpose(2, 0, 1)
                for img in bg_imgs
            ]
        )  # (n, C, H, W)

        inputs = {"input": text_imgs}
        text_embeddings = self.siamese.run(None, inputs)[0]
        inputs = {"input": bg_imgs}
        bg_embeddings = self.siamese.run(None, inputs)[0]
        similarity_matrix = 1 - cdist(text_embeddings, bg_embeddings, metric="cosine")
        similarity_matrix = softmax(similarity_matrix, axis=1)
        mean_sim = similarity_matrix.mean(axis=1)
        std_sim = similarity_matrix.std(axis=1)
        similarity_matrix = (similarity_matrix - mean_sim) / std_sim
        row_ind, col_ind = linear_sum_assignment(-similarity_matrix)
        result_list = sorted(
            [(i, bg_imgs_box[j]) for i, j in zip(row_ind, col_ind)], key=lambda x: x[0]
        )
        match_scores = [similarity_matrix[i, j] for i, j in zip(row_ind, col_ind)]
        return result_list, match_scores


def download_img(url: str) -> bytes:
    response = requests.get(url)
    response.raise_for_status()
    return response.content


def refresh(gt, challenge):
    url = "http://api.geevisit.com/refresh.php"
    params = {"gt": gt, "challenge": challenge, "callback": "geetest_1717918222610"}

    res = requests.get(url, params=params)
    res.raise_for_status()
    match = re.match(r"geetest_1717918222610\((.*)\)", res.text)
    if match is None:
        raise ValueError("Response text does not match the expected format")
    res_json = json.loads(match.group(1))
    data = res_json["data"]
    image_servers = data["image_servers"]
    static_server = image_servers[0]
    pic = data["pic"]
    static_server_url = f"https://{static_server}{pic.lstrip('/')}"
    return static_server_url


def normalize_image(img_np, mean=None, std=None):
    if std is None:
        std = [0.229, 0.224, 0.225]
    if mean is None:
        mean = [0.485, 0.456, 0.406]
    img_np = img_np.astype(np.float32) / 255.0
    for i in range(3):
        img_np[..., i] = (img_np[..., i] - mean[i]) / std[i]
    return img_np


class TripleValidator(Validator):
    def need_api_key(self) -> bool:
        return False

    def have_gt_ui(self) -> bool:
        return False

    def __init__(self, debugDir=None):
        self.model = Model(debugDir=debugDir)
        assert bili_ticket_gt_python
        self.click = bili_ticket_gt_python.ClickPy()

    def validate(self, gt, challenge):
        loguru.logger.info(f"TripleValidator gt: {gt} ; challenge: {challenge}")
        (_, _) = self.click.get_c_s(gt, challenge)
        _type = self.click.get_type(gt, challenge)
        (c, s, args) = self.click.get_new_c_s_args(gt, challenge)
        for _ in range(10):
            try:
                before_calculate_key = time.time()
                pic_content = download_img(args)
                text_imgs, text_boxes, bg_imgs, bg_boxes = self.model.detect(
                    pic_content
                )
                if (
                    len(text_boxes) != len(bg_boxes)
                    or len(text_boxes) == 1
                    or len(bg_boxes) == 1
                ):
                    raise Exception(
                        f"detect error fast retry text_boxes: {len(text_boxes)} bg_boxes: {len(bg_boxes)}"
                    )
                result_list, output_res = self.model.match(text_imgs, bg_imgs, bg_boxes)
                loguru.logger.debug(f"{output_res}")
                point_list = []
                for idx, i in result_list:
                    left = str(round((i[0] + 30) / 333 * 10000))
                    top = str(round((i[1] + 30) / 333 * 10000))
                    point_list.append(f"{left}_{top}")
                w = self.click.generate_w(
                    ",".join(point_list),
                    gt,
                    challenge,
                    str(list(c)),
                    s,
                    "abcdefghijklmnop",
                )
                w_use_time = time.time() - before_calculate_key
                loguru.logger.debug(f"generation time: {w_use_time} seconds")
                if w_use_time < 2:
                    time.sleep(2 - w_use_time)
                msg, validate = self.click.verify(gt, challenge, w)
                if not validate:
                    raise Exception("生成错误")
                loguru.logger.info("本地验证码过码成功")
                return validate
            except Exception as e:
                loguru.logger.info(e)
                args = refresh(gt, challenge)


if __name__ == "__main__":
    # 使用示例
    validator = TripleValidator(
        debugDir=os.path.join(FILES_ROOT_PATH, "geetest", "debug", f"{time.time()}")
    )
    assert bili_ticket_gt_python
    test_validator(validator, bili_ticket_gt_python.ClickBy(), n=100)

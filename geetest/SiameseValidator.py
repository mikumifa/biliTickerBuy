import json
import os.path
import re
import time

import cv2
import loguru
import numpy as np
import onnxruntime
import requests
from scipy.optimize import linear_sum_assignment

from const import APP_PATH
from geetest.Validator import Validator, test_validator
from util.dynimport import bili_ticket_gt_python


# https://github.com/Amorter/biliTicker_gt/blob/f378891457bb78bcacf181eaf642b11f5543b4e0/src/click.rs#L166

class Model:
    def __init__(self, ):
        self.yolo = onnxruntime.InferenceSession(os.path.join(APP_PATH, "geetest", "model", "yolo.onnx"))
        self.siamese = onnxruntime.InferenceSession(os.path.join(APP_PATH, "geetest", "model", "siamese.onnx"))
        self.size = (224, 224)

    def detect(self, img) -> (list[bytes], list[list[int]]):
        confidence_thres = 0.8
        iou_thres = 0.8
        model_inputs = self.yolo.get_inputs()
        input_shape = model_inputs[0].shape
        input_width = input_shape[2]
        input_height = input_shape[3]
        origin_img = cv2.imdecode(np.frombuffer(img, np.uint8), cv2.IMREAD_ANYCOLOR)
        img_height, img_width = origin_img.shape[:2]
        img = cv2.cvtColor(origin_img, cv2.COLOR_BGR2RGB)
        img = cv2.resize(img, (input_height, input_width))
        image_data = np.array(img) / 255.0
        image_data = np.transpose(image_data, (2, 0, 1))
        image_data = np.expand_dims(image_data, axis=0).astype(np.float32)
        output = self.yolo.run(None, {model_inputs[0].name: image_data})
        outputs = np.transpose(np.squeeze(output[0]))
        rows = outputs.shape[0]
        boxes, scores, class_ids = [], [], []
        x_factor = img_width / input_width
        y_factor = img_height / input_height
        for i in range(rows):
            classes_scores = outputs[i][4:]
            max_score = np.amax(classes_scores)
            if max_score >= confidence_thres:
                class_id = np.argmax(classes_scores)
                x, y, w, h = outputs[i][0], outputs[i][1], outputs[i][2], outputs[i][3]
                left = int((x - w / 2) * x_factor)
                top = int((y - h / 2) * y_factor)
                width = int(w * x_factor)
                height = int(h * y_factor)
                class_ids.append(class_id)
                scores.append(max_score)
                boxes.append([left, top, width, height])
        indices = cv2.dnn.NMSBoxes(boxes, scores, confidence_thres, iou_thres)
        ret_boxes = sorted([boxes[i] for i in indices], key=lambda x: x[0])
        text_imgs = []
        text_boxes = []
        bg_imgs = []
        bg_boxes = []
        for i in ret_boxes:
            cropped = origin_img[i[1]: i[1] + i[3], i[0]: i[0] + i[2]]
            if cropped.shape[0] < 35 and cropped.shape[1] < 35:
                text_imgs.append(cropped.astype(np.float32))
                text_boxes.append(i)
            else:
                bg_imgs.append(cropped.astype(np.float32))
                bg_boxes.append(i)
        return text_imgs, text_boxes, bg_imgs, bg_boxes

    def match(self, text_imgs, bg_imgs, bg_imgs_box):
        n = len(text_imgs)

        text_imgs = np.stack(
            [(cv2.resize(img, self.size) / 255).transpose(2, 0, 1) for img in text_imgs])  # (n, C, H, W)
        bg_imgs = np.stack([(cv2.resize(img, self.size) / 255).transpose(2, 0, 1) for img in bg_imgs])  # (n, C, H, W)

        text_batch = np.repeat(text_imgs[:, None, :, :, :], n, axis=1).reshape(n * n, 3, self.size[0],
                                                                               self.size[1])  # (n*n, C, H, W)
        bg_batch = np.repeat(bg_imgs[None, :, :, :, :], n, axis=0).reshape(n * n, 3, self.size[0],
                                                                           self.size[1])  # (n*n, C, H, W)
        inputs = {'img1': text_batch, 'img2': bg_batch}
        outputs = self.siamese.run(None, inputs)[0]
        similarity_matrix = outputs.reshape(n, n)

        row_ind, col_ind = linear_sum_assignment(-similarity_matrix)
        result_list = sorted([(i, bg_imgs_box[j]) for i, j in zip(row_ind, col_ind)], key=lambda x: x[0])
        match_scores = [similarity_matrix[i, j] for i, j in zip(row_ind, col_ind)]
        return result_list, match_scores


def download_img(url: str) -> bytes:
    response = requests.get(url)
    response.raise_for_status()
    return response.content


def refresh(gt, challenge):
    url = "http://api.geevisit.com/refresh.php"
    params = {
        "gt": gt,
        "challenge": challenge,
        "callback": "geetest_1717918222610"
    }

    res = requests.get(url, params=params)
    res.raise_for_status()
    match = re.match(r"geetest_1717918222610\((.*)\)", res.text)
    res_json = json.loads(match.group(1))
    data = res_json["data"]
    image_servers = data["image_servers"]
    static_server = image_servers[0]
    pic = data["pic"]
    static_server_url = f"https://{static_server}{pic.lstrip('/')}"
    return static_server_url


class SiameseValidator(Validator):
    def need_api_key(self) -> bool:
        return False

    def have_gt_ui(self) -> bool:
        return False

    def __init__(self):
        self.model = Model()
        self.click = bili_ticket_gt_python.ClickPy()
        pass

    def validate(self, gt, challenge) -> Exception | str:
        loguru.logger.info(f"SiameseValidator gt: {gt} ; challenge: {challenge}")
        (_, _) = self.click.get_c_s(gt, challenge)
        _type = self.click.get_type(gt, challenge)
        (c, s, args) = self.click.get_new_c_s_args(gt, challenge)
        for _ in range(10):
            try:
                before_calculate_key = time.time()
                pic_content = download_img(args)
                text_imgs, text_boxes, bg_imgs, bg_boxes = self.model.detect(pic_content)
                if len(text_boxes) != len(bg_boxes) or len(text_boxes) == 1 or len(bg_boxes) == 1:
                    raise Exception("fast retry")
                result_list, output_res = self.model.match(text_imgs, bg_imgs, bg_boxes)
                point_list = []
                for idx, i in result_list:
                    left = str(round((i[0] + 30) / 333 * 10000))
                    top = str(round((i[1] + 30) / 333 * 10000))
                    point_list.append(f"{left}_{top}")
                w = self.click.generate_w(",".join(point_list), gt, challenge, str(c), s, "abcdefghijklmnop")
                w_use_time = time.time() - before_calculate_key
                loguru.logger.debug(f"generation time: {w_use_time} seconds")
                if w_use_time < 2:
                    time.sleep(2 - w_use_time)
                msg, validate = self.click.verify(gt, challenge, w)
                if not validate:
                    raise Exception("生成错误")
                loguru.logger.info(f"本地验证码过码成功")
                loguru.logger.debug(f"{output_res}")
                return validate
            except Exception as e:
                loguru.logger.info(e)
                args = refresh(gt, challenge)


if __name__ == "__main__":
    # 使用示例
    validator = SiameseValidator()
    test_validator(validator, n=100)

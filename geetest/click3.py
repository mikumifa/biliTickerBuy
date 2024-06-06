# -*- coding: utf-8 -*-
import io
from pathlib import Path
import requests
from PIL import Image
import ddddocr
from typing import Tuple

def slice_img(img) -> Tuple[Image.Image, Image.Image]:
	if isinstance(img, (str, Path)):
		_img = Image.open(img)
	elif isinstance(img, bytes):
		_img = Image.open(io.BytesIO(img))
	else:
		raise ValueError(f'输入图片类型错误, 必须是<type str>/<type Path>/<type bytes>: {type(img)}')
	background_img = _img.crop((0, 0, 344, 344))
	text_img = _img.crop((0, 345, 116, 384))
	return(background_img, text_img)

class Click3:
	def __init__(self, ocr: ddddocr.DdddOcr = ddddocr.DdddOcr(show_ad=False, beta=True), 
			  det: ddddocr.DdddOcr = ddddocr.DdddOcr(show_ad=False, det=True)):
		self.ocr = ocr
		self.det = det

	def calculated_position(self, img_url):
		img = requests.get(img_url).content

		(background_img, text_img) = slice_img(img)
		text = self.ocr.classification(text_img)
		print(text)
		background_bytes = io.BytesIO()
		background_img.save(background_bytes, format='PNG')
		background_bytes.seek(0)
		bboxes = self.det.detection(background_bytes.read())
		texts = list()
		for bbox in bboxes:
			(x1, y1, x2, y2) = bbox
			img = background_img.crop((x1, y1, x2, y2))
			this_text = self.ocr.classification(img)
			texts.append(this_text)
		print(texts)
		res = list()
		no_finds = list()
		is_find = [False] * texts.__len__()
		for c in text:
			try:
				index = texts.index(c)
			except:
				no_finds.append(c)
				continue
			is_find[index] = True
			position = str(round((bboxes[index][0] + bboxes[index][2]) / 2 / 333.375 * 100 * 100)) + '_' + str(round((bboxes[index][1] + bboxes[index][3]) / 2 / 333.375 * 100 * 100))
			res.append(position)
		for c in no_finds:
			for i in range(len(is_find)):
				if not is_find[i]:
					is_find[i] = True
					position = str(round((bboxes[i][0] + bboxes[i][2]) / 2 / 333.375 * 100 * 100)) + '_' + str(round((bboxes[i][1] + bboxes[i][3]) / 2 / 333.375 * 100 * 100))
					res.append(position)
					break
		print(res)
		return ','.join(res)

if __name__ == '__main__':
	click = Click3()
	img = "https://static.geetest.com/captcha_v3/batch/v3/72556/2024-06-06T05/word/42a62cb4cafb461d92eee08598c13b95.jpg?challenge=a8a9ae907a766d68f9fed4035aab4929"
	print(click.calculated_position(img))
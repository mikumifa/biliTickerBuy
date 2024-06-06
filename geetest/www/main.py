from api import Slide, Click
import subprocess
from slide3 import Slide3
from click3 import Click3
import time
from ddddocr import DdddOcr

def main1():
	api = Slide()
	slide3 = Slide3()

	cmd0 = "node -e \"require('./rt.js').rt()\""
	print(cmd0)
	rt = subprocess.run(cmd0, shell=True, stdout=subprocess.PIPE).stdout.decode('utf-8')
	(challenge, gt) = api.register()

	print(challenge)
	print(gt)
	(c, s) = api.get_c_s(challenge, gt, None)

	api.get_type(challenge, gt, None)

	(c, s, challenge, bg_url, slice_url) = api.get_new_c_s_challenge_bg_slice(challenge, gt)
	dis = slide3.calculated_distance(bg_url, slice_url)
	cmd3 = "node -e \"require('./slide.js').send(" + str(dis) + ",\'" + gt + "\',\'" + challenge + "\'," + str(c) + ",\'" + s + "\',\'"+ rt + "\')\""
	print(cmd3)
	w = subprocess.run(cmd3, shell=True, stdout=subprocess.PIPE).stdout.decode('utf-8')
	time.sleep(2)
	res = api.ajax(challenge, gt, w)
	print(res)

def main2():
	api = Click()
	click3 = Click3()

	cmd0 = "node -e \"require('./rt.js').rt()\""
	print(cmd0)
	rt = subprocess.run(cmd0, shell=True, stdout=subprocess.PIPE).stdout.decode('utf-8')
	(challenge, gt) = api.register()

	print(challenge)
	print(gt)
	(c, s) = api.get_c_s(challenge, gt, None)

	api.get_type(challenge, gt, None)

	(c, s, pic) = api.get_new_c_s_pic(challenge, gt)
	position = click3.calculated_position(pic)
	cmd3 = "node -e \"require('./click.js').send('" + gt + "\',\'" + challenge + "\'," + str(c) + ",\'" + s + "\',\'"+ rt + "\',\'" + position + "\')\""
	print(cmd3)
	w = subprocess.run(cmd3, shell=True, stdout=subprocess.PIPE).stdout.decode('utf-8')
	time.sleep(2)
	res = api.ajax(challenge, gt, w)
	print(res)

def main3():
	api = Click()
	click3 = Click3(DdddOcr(show_ad=False, beta=True))
	count = 0
	for i in range(300):
		cmd0 = "node -e \"require('./rt.js').rt()\""
		rt = subprocess.run(cmd0, shell=True, stdout=subprocess.PIPE).stdout.decode('utf-8')
		(challenge, gt) = api.register()
		(c, s) = api.get_c_s(challenge, gt, None)

		api.get_type(challenge, gt, None)

		(c, s, pic) = api.get_new_c_s_pic(challenge, gt)
		position = click3.calculated_position(pic)
		cmd3 = "node -e \"require('.click.js').send('" + gt + "\',\'" + challenge + "\'," + str(c) + ",\'" + s + "\',\'"+ rt + "\',\'" + position + "\')\""
		w = subprocess.run(cmd3, shell=True, stdout=subprocess.PIPE).stdout.decode('utf-8')
		time.sleep(2)
		res = api.ajax(challenge, gt, w)
		print(res)
		if(res['data']['result'] == 'success'):
			count+=1

	print(count/300)
	
if __name__ == '__main__':
    main3()
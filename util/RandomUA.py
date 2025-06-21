import random

ANDROID_MODELS = [
    "M2101K6G",  # MI 11
    "M2102K1AC",  # MI 11 Pro
    "M2104K10AC",  # MI 11 Ultra
    "M2201123C",  # MI 12
    "M2202K1AC",  # MI 12 Pro
    "M2211133C",  # MI 13
    "M2302K1AC",  # MI 13 Pro
    "M2311133C",  # MI 14
    "M2302K1G",  # Redmi K60
    "M2311K1G",  # Redmi K70
    "SM-S931B",  # Galaxy S25
    "SM-S931U",  # Galaxy S25 (US)
    "SM-S928B",  # Galaxy S24 Ultra
    "SM-S928W",  # Galaxy S24 Ultra (Canada)
    "SM-S921B",  # Galaxy S24
    "SM-S918B",  # Galaxy S23
    "SM-S908B",  # Galaxy S22 Ultra
    "SM-F9560",  # Galaxy Z Flip6
    "SM-F956U",  # Galaxy Z Flip6 (US)
    "SM-F946B",  # Galaxy Z Fold5
    "SM-G556B",  # Galaxy Xcover7
    "SM-A546B",  # Galaxy A54
    "SM-A556B",  # Galaxy A55
    "PGKM10",  # Find X6
    "PGEM10",  # Find X6 Pro
    "PGJM10",  # Find X7
    "PGDM10",  # Find X7 Ultra
    "PFEM10",  # Reno11
    "PGFM10",  # Reno11 Pro
    "V2266A",  # X90
    "V2301A",  # X90 Pro
    "V2309A",  # X100
    "V2324A",  # X100 Pro
    "V2285A",  # S17
    "V2318A",  # S18
    "V2338A",  # iQOO 12
    "DCO-AL00",  # Mate 50
    "BNE-AL00",  # Mate 50 Pro
    "ALN-AL00",  # Mate 60
    "ALN-AL10",  # Mate 60 Pro
    "LNA-AL00",  # P60
    "LNA-AL10",  # P60 Pro
    "PGT-AN10",  # Magic5
    "PGT-AN20",  # Magic5 Pro
    "BVL-AN00",  # Magic6
    "BVL-AN10",  # Magic6 Pro
    "ALI-AN00",  # 90 GT
    "YOK-AN10",  # X50
    "PJD110",  # OnePlus 11
    "PJZ110",  # OnePlus 11 Pro
    "PJA110",  # OnePlus 12
    "CPH2449",  # OnePlus Nord 3
    "CPH2581",  # OnePlus 12R
    "RMX3551",  # realme GT Neo5
    "RMX3708",  # realme 11 Pro
    "2304FPN6DC",  # Redmi Note 12
    "23053RN02A",  # Redmi Note 12 Pro
    "23078RKD5C",  # Redmi K60 Pro
    "ASUS_AI2401",  # ROG Phone 8
    "NE2213",  # Nothing Phone (2)
    "A063",  # Nothing Phone (2a)
]

CHROME_VERSIONS = [
    "109.0.5414.87",
    "110.0.5481.65",
    "111.0.5563.116",
    "112.0.5615.138",
    "113.0.5672.162",
    "114.0.5735.196",
    "115.0.5790.170",
    "116.0.5845.92",
    "117.0.5938.132",
    "118.0.5993.90",
    "119.0.6045.134",
    "120.0.6099.224",
    "121.0.6167.85",
    "122.0.6261.111",
    "123.0.6312.105",
    "124.0.6367.78",
    "125.0.6422.60",
    "126.0.6478.54",
    "127.0.6533.103",
]


# 生成随机构建号
def random_build_number():
    letter = random.choice(["A", "B", "C", "D"])
    date = f"{random.randint(22, 24):02d}{random.randint(1,12):02d}{random.randint(1,28):02d}"
    seq = random.randint(1, 999)
    return f"AP{random.randint(1,9)}{letter}.{date}.{seq:03d}"


# 生成UA
_def_ua_template = (
    "Mozilla/5.0 (Linux; Android {android_version}; {model} Build/{build}; wv) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/{chrome_version} Mobile Safari/537.36 "
    "BiliApp/8500200 mobi_app/android isNotchWindow/1 NotchHeight=32 mallVersion/8500200 mVersion/311 disable_rcmd/0 magent/BILI_H5_ANDROID_{android_version}_8.50.0_8500200"
)


def generate_bili_ua():
    android_version = str(random.randint(11, 15))
    model = random.choice(ANDROID_MODELS)
    build = random_build_number()
    chrome_version = random.choice(CHROME_VERSIONS)
    ua = _def_ua_template.format(
        android_version=android_version,
        model=model,
        build=build,
        chrome_version=chrome_version,
    )
    return ua


# 全局UA变量
_global_ua = None


def get_global_ua():
    global _global_ua
    if _global_ua is None:
        _global_ua = generate_bili_ua()
    return _global_ua

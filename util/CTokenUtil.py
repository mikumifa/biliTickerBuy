import base64
import random
import time

class CTokenGenerator:
    def __init__(self, ticket_collection_t, time_offset, stay_time):
        self.touch_event = 0
        self.isibility_change = 0
        self.page_unload = 0
        self.timer = 0
        self.time_difference = 0
        self.scroll_x = 0
        self.scroll_y = 0
        self.inner_width = 0
        self.inner_height = 0
        self.outer_width = 0
        self.outer_height = 0
        self.screen_x = 0
        self.screen_y = 0
        self.screen_width = 0
        self.screen_height = 0
        self.screen_avail_width = 0
        self.ticket_collection_t = ticket_collection_t
        self.time_offset = time_offset
        self.stay_time = stay_time

    def encode(self):
        buffer = bytearray(16)
        data_mapping = {
            0: {'data': self.touch_event, 'length': 1},
            1: {'data': self.scroll_x, 'length': 1},
            2: {'data': self.isibility_change, 'length': 1},
            3: {'data': self.scroll_y, 'length': 1},
            4: {'data': self.inner_width, 'length': 1},
            5: {'data': self.page_unload, 'length': 1},
            6: {'data': self.inner_height, 'length': 1},
            7: {'data': self.outer_width, 'length': 1},
            8: {'data': self.timer, 'length': 2},
            10: {'data': self.time_difference, 'length': 2},
            12: {'data': self.outer_height, 'length': 1},
            13: {'data': self.screen_x, 'length': 1},
            14: {'data': self.screen_y, 'length': 1},
            15: {'data': self.screen_width, 'length': 1},
        }
        i = 0
        while i < 16:
            if i in data_mapping:
                mapping = data_mapping[i]
                if mapping['length'] == 1:
                    value = min(255, mapping['data']) if mapping['data'] > 0 else mapping['data']
                    buffer[i] = value & 0xFF
                    i += 1
                elif mapping['length'] == 2:
                    value = min(65535, mapping['data']) if mapping['data'] > 0 else mapping['data']
                    buffer[i] = (value >> 8) & 0xFF
                    buffer[i + 1] = value & 0xFF
                    i += 2
            else:
                condition_value = self.scroll_y if (4 & self.screen_height) else self.screen_avail_width
                buffer[i] = condition_value & 0xFF
                i += 1
        data_str = ''.join(chr(b) for b in buffer)
        return self.to_binary(data_str)

    def to_binary(self, data_str):
        uint16_data = []
        uint8_data = []
        # 第一次转换：字符串转为Uint16Array等价物
        for char in data_str:
            uint16_data.append(ord(char))
        # 第二次转换：Uint16Array buffer转为Uint8Array
        for val in uint16_data:
            uint8_data.append(val & 0xFF)
            uint8_data.append((val >> 8) & 0xFF)
        byte_data = bytes(uint8_data)
        return base64.b64encode(byte_data).decode('ascii')

    def generate_ctoken(self, type="createV2") -> str:
        self.touch_event = 255                              # 触摸事件数: 手机端抓包数据
        self.isibility_change = 2                           # 可见性变化数: 手机端抓包数据
        self.inner_width = 255                              # 窗口内部宽度: 手机端抓包数据
        self.inner_height = 255                             # 窗口内部高度: 手机端抓包数据
        self.outer_width = 255                              # 窗口外部宽度: 手机端抓包数据
        self.outer_height = 255                             # 窗口外部高度: 手机端抓包数据
        self.screen_width = 255                             # 屏幕宽度: 手机端抓包数据
        self.screen_height = random.randint(1000, 3000)     # 屏幕高度: 用于条件判断
        self.screen_avail_width = random.randint(1, 100)    # 屏幕可用宽度: 用于条件判断
        if type == "createV2":
            # createV2阶段
            self.time_difference = int(time.time() + self.time_offset - self.ticket_collection_t)
            self.timer = int(self.time_difference + self.stay_time)
            self.page_unload = 25  # 页面卸载数: 手机端抓包数据
        else:
            # prepare阶段
            self.time_difference = 0
            self.timer = int(self.stay_time)
            self.touch_event = random.randint(3, 10)
        return self.encode()
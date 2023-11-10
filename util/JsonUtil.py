import json


class ProjectInfo:
    def __init__(self, data):
        self.data = data["data"]

    def get_name(self):
        return self.data["name"]

    def get_screen_list(self):
        return self.data["screen_list"]

    def get_ticket_info(self):
        raw_list = self.data["screen_list"]


class ProfileInfo:
    def __init__(self, data):
        self.personList = data["data"]["list"]

    def get_persons(self):
        return self.personList

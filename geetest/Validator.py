from abc import ABC, abstractmethod


class Validator(ABC):
    @abstractmethod
    def validate(self, field: str) -> str:
        pass

    @abstractmethod
    def have_gt_ui(self) -> bool:
        pass

    @abstractmethod
    def need_api_key(self) -> bool:
        pass

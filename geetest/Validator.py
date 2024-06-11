from abc import ABC, abstractmethod


class Validator(ABC):
    @abstractmethod
    def validate(self, field: str) -> str:
        pass



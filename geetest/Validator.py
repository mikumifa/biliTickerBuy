import time
from abc import ABC, abstractmethod


class Validator(ABC):
    @abstractmethod
    def validate(self, gt, challenge) -> str:
        pass

    @abstractmethod
    def have_gt_ui(self) -> bool:
        pass

    @abstractmethod
    def need_api_key(self) -> bool:
        pass


def test_validator(
    validator,
    click,
    n=100,
):
    success_count = 0
    total_time = 0
    for i in range(n):
        gt, challenge = click.register_test(
            "https://passport.bilibili.com/x/passport-login/captcha?source=main_web"
        )
        start_time = time.time()
        validate_string = validator.validate(gt, challenge)
        elapsed_time = time.time() - start_time
        total_time += elapsed_time  # type: ignore
        if validate_string:
            success_count += 1
        print(f"Test {i + 1}: Result = {validate_string}, Time = {elapsed_time:.4f}s")
    accuracy = (success_count / n) * 100
    avg_time = total_time / n
    print(f"\n✅ 测试完成，共 {n} 次:")
    print(f"✅ 正确率: {accuracy:.2f}%")
    print(f"✅ 平均时间: {avg_time:.4f}s")
    return validator

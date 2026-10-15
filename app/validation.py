import re


def normalize_cpf(value: str) -> str:
    digits = re.sub(r"\D", "", value)
    if len(digits) != 11 or digits == digits[0] * 11:
        raise ValueError("CPF inválido")

    for position in (9, 10):
        total = sum(int(digits[index]) * (position + 1 - index) for index in range(position))
        check_digit = (total * 10 % 11) % 10
        if check_digit != int(digits[position]):
            raise ValueError("CPF inválido")
    return digits


def mask_cpf(value: str) -> str:
    return f"***.***.***-{value[-2:]}"

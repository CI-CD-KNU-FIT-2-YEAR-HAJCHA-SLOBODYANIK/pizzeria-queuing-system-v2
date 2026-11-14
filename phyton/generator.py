"""Генератор замовлень на один робочий день.

На основі відомих рецептів та добавок із папки data створює JSON-файл
із замовленнями для подальшого імітаційного моделювання.
"""

import argparse
import csv
import json
import random
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OPEN_HOUR = 9
CLOSE_HOUR = 22
STEP_MINUTES = 5

# Використовуємо довільні ваги замість відсотків, оскільки їх зручніше змінювати.
# Програма самостійно перетворює ваги на ймовірності шляхом нормалізації.
# Для пропущених годин застосовується лінійна інтерполяція.
# Години поза робочим днем не генеруються, але можуть бути опорними точками інтерполяції.
HOUR_WEIGHTS = {
    # Поза робочим днем
    8: 40,

    # Ранок — низький попит
    9: 100,
    10: 140,
    11: 260,

    # Обідній пік
    12: 450,
    13: 500,
    14: 350,

    # Післяобідній спад
    15: 230,
    16: 200,
    17: 320,

    # Вечірній пік
    18: 550,
    19: 600,
    20: 420,

    # Завершення робочого дня
    21: 180,

    # Поза робочим днем
    22: 80,
}


"""Зчитує з CSV-файлу поля id, time та price."""
def read_catalog(path):
    result = {}

    with Path(path).open('r', encoding='utf-8-sig', newline='') as file:
        # Відкриваємо таблицю та послідовно зчитуємо її рядки.
        for row in csv.DictReader(file):
            item_id = str(row['id']).strip()

            if not item_id or item_id in result:
                raise ValueError(f'Порожній або повторюваний id у {path}: {item_id!r}')

            cook_time = float(row['time'])
            price = float(row['price'])

            if cook_time < 0 or price < 0:
                raise ValueError(f'Некоректні time/price для {item_id} у {path}')

            result[item_id] = {'time': cook_time, 'price': price}

    if not result:
        raise ValueError(f'За шляхом {path} не знайдено жодного елемента.')

    return result


"""Перетворює число від 0 до 1 на час замовлення з кроком 5 хвилин."""
def generate_time(value, anchors=HOUR_WEIGHTS):
    if not 0 <= value < 1:
        raise ValueError("Значення має бути від 0 до 1 (не включно з 1).")

    if not anchors:
        raise ValueError("Таблиця ваг не може бути порожньою.")

    # Повертаємо вагу години, за відсутності застосовуємо інтерполяцію.
    def weight(hour):
        if hour in anchors:
            return anchors[hour]

        left = [h for h in anchors if h < hour]
        right = [h for h in anchors if h > hour]

        if not left:
            return anchors[min(right)]

        if not right:
            return anchors[max(left)]

        left = max(left)
        right = min(right)

        # Лінійна інтерполяція між найближчими годинами з відомими вагами.
        return anchors[left] + (
            (anchors[right] - anchors[left])
            * (hour - left) / (right - left)
        )

    # Обчислюємо ваги для всіх годин роботи закладу без винятків.
    weights = [weight(h) for h in range(OPEN_HOUR, CLOSE_HOUR)]

    if any(w < 0 for w in weights):
        raise ValueError("Ваги мають бути невід'ємними.")

    total_weight = sum(weights)

    if total_weight <= 0:
        raise ValueError("Сума ваг має бути додатною.")

    position = value * total_weight

    # Перебираємо години від початку до кінця, віднімаючи їхні ваги,
    # доки позиція не потрапить у відповідний часовий проміжок.
    for i, (hour, w) in enumerate(zip(range(OPEN_HOUR, CLOSE_HOUR), weights)):
        if position < w:
            left = weights[max(0, i - 1)]
            right = weights[min(i + 1, len(weights) - 1)]
            k = (right - left) / (left + right + 2 * w)
            u = position / w
            t = 2 * u / (1 - k + ((1 - k)**2 + 4 * k * u)**0.5)

            return hour * 60 + min(60 // STEP_MINUTES - 1, int(t * (60 // STEP_MINUTES))) * STEP_MINUTES

        position -= w


"""Генерує count замовлень на один робочий день."""
def generate_orders(count, seed=None,
                    recipes_path=ROOT / 'data' / 'recipes.csv',
                    toppings_path=ROOT / 'data' / 'toppings.csv',
                    repeat_topping_probability=0.45,
                    custom_probability=0.35):
    if count < 0:
        raise ValueError('Кількість замовлень не може бути від\'ємною.')

    if not 0 <= custom_probability <= 1:
        raise ValueError('Ймовірність індивідуального замовлення має бути від 0 до 1.')

    if not 0 <= repeat_topping_probability <= 1:
        raise ValueError('Ймовірність повторного додавання топінгу має бути від 0 до 1.')

    recipes = read_catalog(recipes_path)
    toppings = read_catalog(toppings_path)

    recipe_ids = list(recipes)
    topping_ids = list(toppings)

    rng = random.Random(seed)
    orders = []

    for order_id in range(1, count + 1):
        minute = generate_time(rng.random())

        # Розподіл Бернуллі визначає індивідуальність замовлення.
        is_custom = rng.random() < custom_probability

        extra_ids = []

        if is_custom and topping_ids:
            available = topping_ids.copy()

            # Додаємо топінги, доки залишаються ще не вибрані.
            while available:
                extra_ids.append(
                    available.pop(rng.randrange(len(available)))
                )

                # Продовжуємо додавання з імовірністю repeat_topping_probability.
                # В іншому випадку припиняємо вибір топінгів.
                if rng.random() >= repeat_topping_probability:
                    break

        orders.append({
            'id': order_id,
            'minute': minute,
            'recipe_id': rng.choice(recipe_ids), # Випадковий рецепт із каталогу.
            'toppings': extra_ids,
        })

    # Сортуємо замовлення за часом, щоб не робити цього в симуляторі.
    return sorted(orders, key=lambda order: (order['minute'], order['id']))


"""Зберігає замовлення у JSON-файл та повертає шлях до нього."""
def save_orders(orders, folder=ROOT / 'output' / 'generated'):
    folder = Path(folder)

    # Створюємо папку, якщо вона ще не існує.
    folder.mkdir(parents=True, exist_ok=True)

    # Додаємо часову позначку до назви файлу.
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S-%f')

    path = folder / f'Generation_{len(orders)}orders-{stamp}.json'

    path.write_text(
        json.dumps(orders, ensure_ascii=False, indent=2),
        encoding='utf-8'
    )

    return path

"""Завантажує замовлення з JSON-файлу (для інших модулів)."""
def load_orders(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Генерація замовлень на один день.')
    parser.add_argument(
        'count',
        type=int,
        help='Кількість замовлень за день'
    )
    parser.add_argument(
        '--seed',
        type=int,
        default=None,
        help='Сід; за замовчуванням формується на основі часу'
    )

    args = parser.parse_args()
    seed = args.seed if args.seed is not None else time.time_ns()
    path = save_orders(generate_orders(args.count, seed))

    print(f'Сід: {seed}\nСтворено: {path}')

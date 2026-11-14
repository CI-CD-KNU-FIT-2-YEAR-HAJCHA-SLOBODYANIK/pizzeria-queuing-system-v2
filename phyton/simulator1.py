
"""Модель 1 піч, черга на 10 замовлень."""

from datetime import datetime
import argparse
import csv
import json
from collections import deque
from pathlib import Path

from generator import CLOSE_HOUR, OPEN_HOUR, ROOT, STEP_MINUTES, load_orders, read_catalog # Часові параметри краще брати з run.py, а не з генератора
END_HOUR = 24
QUEUE_LIMIT = 10
CLOSE_HOUR = min(CLOSE_HOUR, END_HOUR)

"""Завантажує результати симуляції з JSON-файлу. Це для інших модулів."""
def load_simulation(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))

"""Попередньо обчислює тривалість за каталогами, щоб симуляція була швидкою."""
def prepare_orders(orders, recipes, toppings):
    prepared = []
    seen_ids = set()
    for order in orders:
        order_id = int(order['id'])
        minute = int(order['minute'])

        if order_id in seen_ids:
            raise ValueError(f'Повторюваний ID замовлення: {order_id}')

        # Замовлення поза часовими межами ми не відхиляємо, симуляція його просто не розгляне.
        
        recipe = recipes[str(order['recipe_id'])]
        extra_time = sum(toppings[str(item_id)]['time'] for item_id in order['toppings'])
        duration = recipe['time'] + extra_time
        if duration <= 0:
            raise ValueError(f'Некоректна тривалість замовлення: {order_id}')

        prepared.append((minute, order_id, duration))
        seen_ids.add(order_id)
    return sorted(prepared, key=lambda item: (item[0], item[1])) # Тут усе-таки додано сортування за часом, але там і так усе відсортовано


"""Симуляція: піч працює - працює черга - нові замовлення - намагаємося розмістити замовлення в печі
і так по колу.

Після завершення робочого дня піч продовжує обслуговувати чергу.
Поза часовими межами замовлення не розглядаються.
Повертаємо масив часу роботи у хвилинах для печі та масив статусів *розглянутих* замовлень (прийнято/відхилено).
Черга за принципом FIFO.
"""
def simulate(prepared_orders):
    remaining = 0.0
    cooking_id = None
    oven_minutes = 0.0
    queue = deque()
    statuses = []
    status_by_id = {}
    pointer = 0
    while pointer < len(prepared_orders) and prepared_orders[pointer][0] < OPEN_HOUR * 60:
        pointer += 1

    for minute in range(OPEN_HOUR * 60, END_HOUR * 60 + 1, STEP_MINUTES): # Симулюємо залишок дня до END_HOUR, щоб завершити всю чергу.

        # Виконуємо приготування протягом наступних 5 хвилин.
        if minute > OPEN_HOUR * 60: # першу ітерацію ігноруємо
            # піч вимикається після завершення робочого дня лише за умови порожньої черги
            enabled = minute < CLOSE_HOUR * 60 or len(queue) > 0

            if enabled:
                oven_minutes += STEP_MINUTES
            else:
                if cooking_id is not None:
                    oven_minutes += min(STEP_MINUTES, remaining)

            remaining = max(-STEP_MINUTES, remaining - STEP_MINUTES)
            if remaining <= 0 and cooking_id is not None:
                status_by_id[cooking_id]['completion_minute'] = minute + remaining
                cooking_id = None

            if cooking_id is None:
                if len(queue) > 0 and enabled:
                    order_id, duration = queue.popleft()
                    cooking_id = order_id
                    # Враховуємо час, який ми чекали після завершення, як час, який можемо витратити на приготування:
                    remaining += duration
                    # Якщо час на замовлення раптом менший за STEP_MINUTES, то зменшувати треба STEP_MINUTES, а не змінювати функціонал.

        # Приймаємо всі замовлення, що надійшли в поточний момент.
        if minute < CLOSE_HOUR * 60: # Ну, якщо ми ще не закрилися
            while pointer < len(prepared_orders) and prepared_orders[pointer][0] <= minute:
                if(prepared_orders[pointer][0]) != minute:
                    pointer += 1
                    continue
                _, order_id, duration = prepared_orders[pointer]
                pointer += 1

                accepted = len(queue) < QUEUE_LIMIT

                if accepted:
                    if cooking_id is not None: # Якщо піч зайнята (тобто черга не порожня)
                        if len(queue) < QUEUE_LIMIT:
                            queue.append((order_id, duration)) # Додаємо до черги, якщо не перевищуємо ліміт
                    else:
                        # Інакше відразу призначаємо піч, але без додавання від'ємного remaining.
                        cooking_id = order_id
                        remaining = duration

                status = {
                    'id': order_id,
                    'accepted': accepted,
                    'completion_minute': None,
                }
                statuses.append(status)
                status_by_id[order_id] = status

        if minute >= CLOSE_HOUR * 60:
            if not queue and cooking_id is None:
                break

    return [oven_minutes], statuses


"""Зберігає результати симуляції в один JSON-файл для аналізатора."""
def save_simulation(oven_minutes, statuses, generation_path,
                    folder=ROOT / 'output' / 'simulated'):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True) # Створюємо папку, якщо її ще немає

    stamp = datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    path = folder / f'Simulator_{stamp}_{Path(generation_path).stem}_results.json'

    result = {
        'generation': Path(generation_path).name,
        'oven_minutes': oven_minutes,
        'total_oven_minutes': sum(oven_minutes),
        'total_orders': len(statuses),
        'accepted': sum(order['accepted'] for order in statuses),
        'rejected': sum(not order['accepted'] for order in statuses),
        'completed': sum(order['completion_minute'] is not None for order in statuses),
        'orders': statuses,
    }

    path.write_text(json.dumps(result, indent=2), encoding='utf-8')
    return path


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Симуляція піцерії за готовим JSON.')
    parser.add_argument('orders', type=Path, help='JSON замовлень')
    args = parser.parse_args()

    recipes = read_catalog(ROOT / 'data' / 'recipes.csv')
    toppings = read_catalog(ROOT / 'data' / 'toppings.csv')

    prepared = prepare_orders(load_orders(args.orders), recipes, toppings)

    oven_minutes, statuses = simulate(prepared)

    path = save_simulation(oven_minutes, statuses, args.orders)








































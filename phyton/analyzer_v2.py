"""Аналіз результатів симуляції (з декількома печами), побудова графіків."""

import numpy as np
from scipy.signal import savgol_filter

from generator import ROOT, load_orders, read_catalog
from simulator_v2 import schedule_text, load_simulation


"""Обчислює виручку за завершені замовлення"""
def revenue_for_results(orders, statuses, recipes, toppings):
    accepted_ids = {
        int(row['id']) for row in statuses
        if row['accepted'] and row['completion_minute'] is not None
    }
    return sum(
        recipes[str(order['recipe_id'])]['price'] +
        sum(toppings[str(topping_id)]['price'] for topping_id in order['toppings'])
        for order in orders if int(order['id']) in accepted_ids
    )


"""Отримує шляхи генерацій і симуляцій, виводить статистику текстом та у вигляді графіків."""
def analyze_runs(records, hourly_oven_price,
                 recipes_path=ROOT / 'data' / 'recipes.csv',
                 toppings_path=ROOT / 'data' / 'toppings.csv'):

    if not records:
        raise ValueError('Потрібні результати прогонів')

    recipes = read_catalog(recipes_path)
    toppings = read_catalog(toppings_path)
    rows = []

    for record in records:
        orders = load_orders(record['generation'])
        result = load_simulation(record['simulation'])

        statuses = result['orders']

        source_ids = {int(order['id']) for order in orders}
        status_ids = {int(order['id']) for order in statuses}

        if not status_ids <= source_ids:
            raise ValueError(f'Невідомі ID замовлень у {record["simulation"]}')

        gross = revenue_for_results(orders, statuses, recipes, toppings) # Обчислюємо виручку
        oven_minutes = float(result['total_oven_minutes'])
        oven_cost = oven_minutes / 60 * hourly_oven_price

        # Можлива виручка від усіх створених замовлень без вирахування витрат.
        possible_gross = sum(
            recipes[str(order['recipe_id'])]['price'] +
            sum(toppings[str(topping_id)]['price'] for topping_id in order['toppings'])
            for order in orders
        )

        rows.append({
            'count': len(orders),
            'accepted': sum(bool(order['accepted']) for order in statuses),
            'rejected': sum(not order['accepted'] for order in statuses),
            'completed': sum(order['completion_minute'] is not None for order in statuses),
            'gross': gross,
            'possible_gross': possible_gross,
            'oven_minutes': oven_minutes,
            'oven_cost': oven_cost,
            'net': gross - oven_cost,
            'schedule': result['schedule'],
        })

    rows.sort(key=lambda row: row['count'])

    print('\nРЕЗУЛЬТАТИ СИМУЛЯЦІЙ (ДЕКІЛЬКА ПЕЧЕЙ)')
    if all(row['schedule'] == rows[0]['schedule'] for row in rows):
        print(f'Розклад печей: {schedule_text(rows[0]["schedule"])}')

    print(f'{"Створено":>9} {"Прийнято":>9} {"Відмов":>8} {"Готово":>8} '
          f'{"Виручка":>12} {"Витрати":>12} {"Прибуток":>12}')

    for row in rows:
        print(f'{row["count"]:>9} {row["accepted"]:>9} {row["rejected"]:>8} '
              f'{row["completed"]:>8} {row["gross"]:>12.2f} '
              f'{row["oven_cost"]:>12.2f} {row["net"]:>12.2f}')

    mean_net = sum(row['net'] for row in rows) / len(rows)
    print(f'Середній чистий прибуток: {mean_net:.2f} грн')
    print('Виручка розраховується за прийняті та завершені замовлення.')

    return rows

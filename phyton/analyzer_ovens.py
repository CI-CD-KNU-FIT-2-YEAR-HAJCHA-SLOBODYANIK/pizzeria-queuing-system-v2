"""Порівняння результатів симуляції для 1–10 печей на однакових генераціях."""

import numpy as np

from simulator_v2 import load_simulation
from generator import ROOT, load_orders, read_catalog


"""Групує результати за кількістю печей і будує складені стовпці."""
def analyze_ovens(records, hourly_oven_price,
                  recipes_path=ROOT / 'data' / 'recipes.csv',
                  toppings_path=ROOT / 'data' / 'toppings.csv'):
    if not records:
        raise ValueError('Потрібні результати прогонів')

    recipes = read_catalog(recipes_path)
    toppings = read_catalog(toppings_path)
    generations = {}
    rows = []

    for record in records:
        path = record['generation']
        if path not in generations:
            orders = load_orders(path)
            prices = {
                int(order['id']): recipes[str(order['recipe_id'])]['price'] +
                sum(toppings[str(item)]['price'] for item in order['toppings'])
                for order in orders
            }
            generations[path] = (len(orders), prices, sum(prices.values()))

        count, prices, possible_gross = generations[path]
        result = load_simulation(record['simulation'])
        statuses = result['orders']

        if not {int(s['id']) for s in statuses} <= prices.keys():
            raise ValueError(f'Невідомі ID замовлень у {record["simulation"]}')

        gross = sum(
            prices[int(s['id'])] for s in statuses
            if s['accepted'] and s['completion_minute'] is not None
        )
        oven_cost = float(result['total_oven_minutes']) / 60 * hourly_oven_price

        rows.append({
            'run_index': record['run_index'],
            'ovens': record['ovens'],
            'count': count,
            'gross': gross,
            'possible_gross': possible_gross,
            'net': gross - oven_cost,
        })

    by_run = {}
    for row in rows: 
        by_run.setdefault(row['run_index'], {})[row['ovens']] = row

    run_ids = sorted(by_run, key=lambda i: by_run[i][1]['count'])
    if any(set(by_run[i]) != set(range(1, 11)) for i in run_ids):
        raise ValueError('Для кожної генерації потрібні результати для 1–10 печей.')

    # П'ять інтервалів за кількістю замовлень; кожен стовпець — середнє інтервалу.
    groups = [part.tolist() for part in np.array_split(run_ids, min(5, len(run_ids)))]
    middle_counts = [
        round(np.mean([by_run[i][1]['count'] for i in group]))
        for group in groups
    ]

    # Ну і ось ГРАФІК
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(15, 7))
    x = np.arange(1, 11)
    width = 0.17
    bottom_ticks = []
    bottom_labels = []
    lowest, highest = 0, 0

    for index, group in enumerate(groups):
        data = [[by_run[i][oven] for i in group] for oven in range(1, 11)]
        gross = np.array([np.mean([r['gross'] for r in part]) for part in data])
        possible = np.array([np.mean([r['possible_gross'] for r in part]) for part in data])
        net = np.array([np.mean([r['net'] for r in part]) for part in data])
        position = x + (index - (len(groups) - 1) / 2) * width
        bottom_ticks.extend(position)
        bottom_labels.extend([str(middle_counts[index])] * len(x))
        lowest = min(lowest, float(net.min()))
        highest = max(highest, float(possible.max()))

        red = np.maximum(net, 0)
        blue = gross - red
        yellow = possible - gross

        ax.bar(position, red, width, color='#d63838', linewidth=0,
               label='Чистий прибуток' if index == 0 else None)
        ax.bar(position, blue, width, bottom=red, color='#0756c8', linewidth=0,
               label='Виручка понад прибуток' if index == 0 else None)
        ax.bar(position, yellow, width, bottom=gross, color='#e5ae00', linewidth=0,
               label='Можлива виручка понад фактичну' if index == 0 else None)
        ax.bar(position, np.minimum(net, 0), width, color="#9c153e", linewidth=0),

    ax.set(
        title=f'Порівняння 1–10 печей: {len(run_ids)} генерацій, {len(rows)} симуляцій',
        xlabel='Середня кількість замовлень',
        ylabel='Гривні (грн)'
    )
    ax.set_xticks(bottom_ticks, bottom_labels, rotation=90, fontsize=8)
    top_axis = ax.secondary_xaxis('top')
    top_axis.set_xticks(x, [str(oven) for oven in x])
    top_axis.set_xlabel('Кількість печей')
    margin = (highest - lowest or 1) * 0.08
    ax.set_ylim(lowest - margin if lowest < 0 else 0, highest + margin)
    ax.axhline(0, color='black', linewidth=0.8)
    ax.grid(axis='y', alpha=0.25)
    ax.legend(loc='upper left')
    fig.tight_layout()
    plt.show(block=False)

    return rows

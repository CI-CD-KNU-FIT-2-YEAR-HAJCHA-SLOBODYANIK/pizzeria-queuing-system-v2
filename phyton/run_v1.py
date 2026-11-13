"""Запуск генерацій і симуляцій з однією піччю."""

import time

from analyzer_v1 import analyze_runs
from generator import ROOT, generate_orders, read_catalog, save_orders
from simulator_v1 import prepare_orders, save_simulation, simulate


DEFAULTS = {
    'min_orders': 20,
    'max_orders': 500,
    'runs': 100,
    'seed': time.time_ns(),
    'oven_price': 180.0,
    'custom_probability': 0.35,
    'repeat_topping_probability': 0.45,
}


"""Створює серію замовлень, запускає симулятор і повертає шляхи JSON."""
def run_experiment(settings, progress=print):
    low = settings['min_orders']
    high = settings['max_orders']
    runs = settings['runs']

    if low < 0 or high < low or runs < 1:
        raise ValueError('Некоректна кількість замовлень або прогонів.')

    for key in ('custom_probability', 'repeat_topping_probability'):
        if not 0 <= settings[key] <= 1:
            raise ValueError(f'{key} має бути в діапазоні від 0 до 1.')

    counts = ([low] if runs == 1 else
              [round(low + (high - low) * i / (runs - 1)) for i in range(runs)])

    recipes = read_catalog(ROOT / 'data' / 'recipes.csv')
    toppings = read_catalog(ROOT / 'data' / 'toppings.csv')
    records = []

    progress(f'Замовлення за прогонами: {counts}')
    progress(f'Початковий seed: {settings["seed"]}; кожний наступний +1')

    for index, count in enumerate(counts):
        orders = generate_orders(
            count,
            seed=settings['seed'] + index, # Початковий seed + індекс прогону
            custom_probability=settings['custom_probability'],
            repeat_topping_probability=settings['repeat_topping_probability'],
        )

        generation_path = save_orders(orders)
        prepared = prepare_orders(orders, recipes, toppings)
        oven_minutes, statuses = simulate(prepared)
        simulation_path = save_simulation(oven_minutes, statuses, generation_path)

        records.append({
            'generation': generation_path,
            'simulation': simulation_path
        })

        progress(f'Прогін {index + 1}/{runs}: {count} замовлень; '
                 f'прийнято {sum(row["accepted"] for row in statuses)}, '
                 f'відмовлено {sum(not row["accepted"] for row in statuses)}')

    return records


"""Графічний інтерфейс запуску симуляцій."""
def launch_gui():
    import tkinter as tk
    from tkinter import messagebox, ttk

    root = tk.Tk()
    root.title('Піцерія. Етап 1 — одна піч')
    root.geometry('650x510')

    frame = ttk.Frame(root, padding=16)
    frame.pack(fill='both', expand=True)

    ttk.Label(
        frame,
        text='Моделювання роботи однієї печі',
        font=('Segoe UI', 14, 'bold')
    ).pack(anchor='w', pady=(0, 10))

    fields = {}
    form = ttk.Frame(frame)
    form.pack(fill='x')

    labels = {
        'min_orders': 'Мінімум замовлень',
        'max_orders': 'Максимум замовлень',
        'runs': 'Кількість прогонів',
        'seed': 'Початковий seed',
        'oven_price': 'Вартість печі (грн/год)',
        'custom_probability': 'Імовірність індивідуальної піци',
        'repeat_topping_probability': 'Імовірність наступного топінгу',
    }

    # Створюємо поля введення за допомогою циклу.
    for i, (key, label) in enumerate(labels.items()):
        ttk.Label(form, text=label).grid(row=i, column=0, sticky='w', pady=4)

        entry = ttk.Entry(form, width=27)
        entry.insert(0, str(DEFAULTS[key]))
        entry.grid(row=i, column=1, sticky='ew', padx=(16, 0), pady=4)

        fields[key] = entry

    form.columnconfigure(1, weight=1)

    log = tk.Text(frame, height=10, wrap='word', state='normal')
    log.pack(side='bottom', fill='both', expand=True, pady=(12, 0))

    # Виводимо повідомлення в консоль і графічний інтерфейс.
    def progress(message):
        log.insert('end', str(message) + '\n')
        log.see('end')
        root.update_idletasks()
        print(message)

    def start():
        try:
            settings = {
                'min_orders': int(fields['min_orders'].get()),
                'max_orders': int(fields['max_orders'].get()),
                'runs': int(fields['runs'].get()),
                'seed': int(fields['seed'].get()),
                'oven_price': float(fields['oven_price'].get().replace(',', '.')),
                'custom_probability': float(fields['custom_probability'].get().replace(',', '.')),
                'repeat_topping_probability': float(fields['repeat_topping_probability'].get().replace(',', '.')),
            }

            records = run_experiment(settings, progress)
            rows = analyze_runs(records, settings['oven_price'])

            progress(f'Середній чистий прибуток: '
                     f'{sum(row["net"] for row in rows) / len(rows):.2f} грн')

        except Exception as exc:
            messagebox.showerror('Помилка', str(exc))

    button = ttk.Button(
        frame,
        text='Запустити генерацію, симуляцію та аналіз',
        command=start
    )
    button.pack(anchor='w', pady=(12, 0))

    root.mainloop()


if __name__ == '__main__':
    launch_gui()
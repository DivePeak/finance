import csv
from decimal import Decimal

total_buys = Decimal('0')
total_fees = Decimal('0')
total_payments = Decimal('0')
total_dividends = Decimal('0')
total_reinvestments = Decimal('0')
total_sells_credit = Decimal('0')

with open('data.csv', 'r') as f:
    reader = csv.DictReader(f)
    holdings = {}
    for row in reader:
        tx_type = row['Transaction']
        symbol = row['Symbol']
        if not symbol: continue
        
        if symbol not in holdings:
            holdings[symbol] = {'units': Decimal('0'), 'cost_base': Decimal('0')}
        
        h = holdings[symbol]
        debit = Decimal(row['Debit'] or '0')
        credit = Decimal(row['Credit'] or '0')
        units = Decimal(row['Units'] or '0')
        price = Decimal(row['Price'] or '0')
        fee = Decimal(row['Fee'] or '0')

        if tx_type == 'Buy':
            h['units'] += units
            h['cost_base'] += debit
        elif tx_type == 'Sell':
            if h['units'] > 0:
                avg_cost = h['cost_base'] / h['units']
                h['cost_base'] -= units * avg_cost
            h['units'] -= units
        elif tx_type in ['Reinvestment', 'Reinvest']:
            h['units'] += units
            h['cost_base'] += units * price

    total_cost_base = sum(h['cost_base'] for h in holdings.values() if h['units'] > 0)
    print(f"Total App Style Cost Base: {total_cost_base}")

    # What if dividends reduce cost base?
    holdings_div = {}
    for row in csv.DictReader(open('data.csv', 'r')):
        tx_type = row['Transaction']
        symbol = row['Symbol']
        if not symbol: continue
        if symbol not in holdings_div: holdings_div[symbol] = {'units': Decimal('0'), 'cost_base': Decimal('0')}
        h = holdings_div[symbol]
        debit = Decimal(row['Debit'] or '0')
        credit = Decimal(row['Credit'] or '0')
        units = Decimal(row['Units'] or '0')
        price = Decimal(row['Price'] or '0')
        if tx_type == 'Buy':
            h['units'] += units
            h['cost_base'] += debit
        elif tx_type == 'Sell':
            if h['units'] > 0:
                h['cost_base'] -= units * (h['cost_base'] / h['units'])
            h['units'] -= units
        elif tx_type in ['Reinvestment', 'Reinvest']:
            h['units'] += units
            h['cost_base'] += units * price
        elif tx_type in ['Payment', 'Dividend']:
            h['cost_base'] -= credit

    # Method 3: Total Buys (as seen before)
    # total_buys was 55359.89

    # Method 4: Total Buys - Total Sells (Proceeds)
    holdings_proceeds = {}
    for row in csv.DictReader(open('data.csv', 'r')):
        tx_type = row['Transaction']
        symbol = row['Symbol']
        if not symbol: continue
        if symbol not in holdings_proceeds: holdings_proceeds[symbol] = {'units': Decimal('0'), 'cost_base': Decimal('0')}
        h = holdings_proceeds[symbol]
        debit = Decimal(row['Debit'] or '0')
        credit = Decimal(row['Credit'] or '0')
        units = Decimal(row['Units'] or '0')
        if tx_type == 'Buy':
            h['units'] += units
            h['cost_base'] += debit
        elif tx_type == 'Sell':
            h['units'] -= units
            h['cost_base'] -= credit
        elif tx_type in ['Reinvestment', 'Reinvest']:
            h['units'] += Decimal(row['Units'] or '0')
            h['cost_base'] += Decimal(row['Units'] or '0') * Decimal(row['Price'] or '0')

    # Method 5: Simple Sum of ALL Buys (ignore sells)
    total_buys_simple = Decimal('0')
    for row in csv.DictReader(open('data.csv', 'r')):
        if row['Transaction'] == 'Buy':
            total_buys_simple += Decimal(row['Debit'] or '0')
    print(f"Simple Sum of all Buys: {total_buys_simple}")

    # Method 6: Total Buys - Dividends (as reduction)
    # total_buys_simple - total_payments (2498.86) = 52861.03
    
    # Method 7: Total Buys + Reinvestments
    reinv_sum = Decimal('0')
    for row in csv.DictReader(open('data.csv', 'r')):
        if row['Transaction'] in ['Reinvestment', 'Reinvest']:
            reinv_sum += Decimal(row['Units'] or '0') * Decimal(row['Price'] or '0')
    print(f"Total Reinvestments Sum: {reinv_sum}")
    # Method 8: App Style but don't adjust cost base for sells
    holdings_no_sell_adj = {}
    for row in csv.DictReader(open('data.csv', 'r')):
        tx_type = row['Transaction']
        symbol = row['Symbol']
        if not symbol: continue
        if symbol not in holdings_no_sell_adj: holdings_no_sell_adj[symbol] = {'units': Decimal('0'), 'cost_base': Decimal('0')}
        h = holdings_no_sell_adj[symbol]
        debit = Decimal(row['Debit'] or '0')
        units = Decimal(row['Units'] or '0')
        price = Decimal(row['Price'] or '0')
        if tx_type == 'Buy':
            h['units'] += units
            h['cost_base'] += debit
        elif tx_type == 'Sell':
            h['units'] -= units
            # NO cost base reduction
        elif tx_type in ['Reinvestment', 'Reinvest']:
            h['units'] += units
            h['cost_base'] += units * price

    total_cost_no_sell_adj = sum(h['cost_base'] for h in holdings_no_sell_adj.values() if h['units'] > 0)
    print(f"Total Cost Base (No sell adjustment): {total_cost_no_sell_adj}")

print(f"Total Buys (incl fees if in Debit): {total_buys}")
print(f"Total Payments (Dividends): {total_payments}")
print(f"Total Dividends (Type 'Dividend'): {total_dividends}")
print(f"Total Reinvestments: {total_reinvestments}")
print(f"Total Sells (Credit): {total_sells_credit}")

expected_cost_base = total_buys + total_reinvestments
# If user expects cost base 55359.89
print(f"Sum (Buys + Reinvest): {expected_cost_base}")
print(f"Sum (Buys + Reinvest - Payments - Dividends): {expected_cost_base - total_payments - total_dividends}")

import pandas as pd
import numpy as np
from datetime import datetime  # Viktig import för datumhantering

# Inställningar för varje uke och block
WEEKS = ['Uke 1', 'Uke 2', 'Uke 3', 'Uke 4']
DAYS = ['Mandag', 'Tirsdag', 'Onsdag', 'Torsdag', 'Fredag', 'Lørdag', 'Søndag']
CATEGORY_MAP = {'Kjøtt': 'Kjott', 'Kjøtt.': 'Kjott'}

# Kolumnmappning för middag per uke (0-index)
MIDDAG_MAP = {
    'Uke 1': {'day': 11, 'cat': 11, 'dish': 14},
    'Uke 2': {'day': 13, 'cat': 13, 'dish': 15},
    'Uke 3': {'day': 13, 'cat': 13, 'dish': 16},
    'Uke 4': {'day': 7,  'cat': 8,  'dish': 10},  # OBS! Avvikande struktur
}

def clean_category(cat):
    if pd.isna(cat):
        return ''
    cat = str(cat).strip()
    return CATEGORY_MAP.get(cat, cat)

def is_valid_row(dag, kategori, rett):
    etiketter = ['Navn:', 'Oppskriftsreferanse', 'Kategori:', 'Kommentar']
    if any(str(rett).startswith(e) for e in etiketter):
        return False
    if any(x in str(rett) for x in ['Lunsj uke', 'Middag uke']):
        return False
    if dag not in DAYS:
        return False
    if kategori in DAYS:
        return False
    return True

rows = []

excel_file = 'meny cosl sommer 2025.xlsx'


for uke in WEEKS:
    df = pd.read_excel(excel_file, sheet_name=uke, header=None)
    # Lunch: alltid samma kolumner, med current_day-logik
    current_day = ''
    for i in range(len(df)):
        dag_cell = df.iat[i, 0]
        dag = str(dag_cell).strip() if not pd.isna(dag_cell) else ''
        if dag in DAYS:
            current_day = dag
        else:
            dag = current_day
        kategori = clean_category(df.iat[i, 1])
        rett = str(df.iat[i, 3]).strip() if not pd.isna(df.iat[i, 3]) else ''
        if is_valid_row(dag, kategori, rett):
            rows.append({'Uke': uke[-1], 'Dag': dag, 'Måltid': 'Lunch', 'Kategori': kategori, 'Rett': rett})

    # Middag: olika kolumner per uke, med current_day-logik
    m = MIDDAG_MAP[uke]
    current_day = ''
    for i in range(len(df)):
        dag_cell = df.iat[i, m['day']]
        dag = str(dag_cell).strip() if not pd.isna(dag_cell) else ''
        if dag in DAYS:
            current_day = dag
        else:
            dag = current_day
        kategori = clean_category(df.iat[i, m['cat']])
        rett = str(df.iat[i, m['dish']]).strip() if not pd.isna(df.iat[i, m['dish']]) else ''
        if is_valid_row(dag, kategori, rett):
            rows.append({'Uke': uke[-1], 'Dag': dag, 'Måltid': 'Middag', 'Kategori': kategori, 'Rett': rett})

out = pd.DataFrame(rows)

out.to_csv('meny_ai_long.csv', index=False, encoding='utf-8-sig', quoting=1)
out.to_csv('meny_ai_long.tsv', index=False, sep='\t', encoding='utf-8-sig', quoting=1)
out.to_excel('meny_ai_long.xlsx', index=False)

print('Antal rader per (Uke, Dag, Måltid):')
print(out.groupby(['Uke', 'Dag', 'Måltid']).size())

print('\nKontroll: Uke 4 Middag (ska vara 3 rader per dag):')
uke4_middag = out[(out['Uke'] == '4') & (out['Måltid'] == 'Middag')]
print(uke4_middag.groupby('Dag').size())

print('\nExempelrad:')
print(out[(out['Uke'] == '4') & (out['Dag'] == 'Mandag') & (out['Måltid'] == 'Middag') & (out['Kategori'] == 'Fisk')])

print('\nFelaktiga Dag-värden:')
print(out[out['Dag'].isin(['Suppe', 'Fisk', 'Kjott'])])

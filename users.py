import os

name = ''
users = 'user_list.txt'

def check_name(name, users):
    name = str(name)
    # Ensure users file exists
    if not os.path.exists(users):
        open(users, 'w', encoding='utf-8').close()
    # Проверяем, есть ли имя в файле
    with open(users, 'r', encoding='utf-8') as file:
        names = [n for n in file.read().splitlines() if n]
    if name in names:
        print('Имя уже существует в файле.')
    else:
        # Если имени нет, добавляем его в файл
        with open(users, 'a', encoding='utf-8') as file:
            file.write(name + '\n')
        print('Имя добавлено в файл.')

def remove_user(name, users):
    name = str(name)
    if not os.path.exists(users):
        return
    with open(users, 'r', encoding='utf-8') as file:
        names = [n for n in file.read().splitlines() if n]
    if name in names:
        names = [n for n in names if n != name]
        with open(users, 'w', encoding='utf-8') as file:
            for n in names:
                file.write(n + '\n')
        print('Имя удалено из файла.')
    else:
        print('Имя не найдено в файле.')
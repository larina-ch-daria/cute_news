name = ''
users = 'user_list.txt'
text = open(users, 'r')

def check_name(name, users):
    name = str(name)
    # Проверяем, есть ли имя в файле
    with open(users, 'r') as file:
        names = file.read().split('\n')
        if name in names:
            print('Имя уже существует в файле.')
        else:
            # Если имени нет, добавляем его в файл
            with open(users, 'a') as file:
                file.write(name + '\n')
            print('Имя добавлено в файл.')
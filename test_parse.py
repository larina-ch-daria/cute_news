import traceback
from cute_news import parse

if __name__ == "__main__":
    try:
        parse()
        try:
            with open('news_list.txt','r',encoding='utf-8') as f:
                print('---NEWS_FILE_START---')
                print(f.read())
                print('---NEWS_FILE_END---')
        except FileNotFoundError:
            print('<news_list.txt not found>')
    except Exception as e:
        print('EXCEPTION while running parse():', e)
        traceback.print_exc()

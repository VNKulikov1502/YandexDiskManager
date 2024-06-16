import telebot
import requests
import os
import json
from cryptography.fernet import Fernet
from dotenv import load_dotenv
import tempfile
from http import HTTPStatus
import logging

# Настройка логгера
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

# Создание обработчика для вывода в консоль
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)
# Загрузка переменных окружения из файла .env
load_dotenv()

# Получение токена бота и ключа шифрования из переменной окружения
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
ENCRYPTION_KEY = os.getenv('ENCRYPTION_KEY').encode()  # Ключ шифрования

INSTRUCTION_FOLDER = 'instruction'

# Пути к файлам инструкции
INSTRUCTION_TEXT_FILE = os.path.join(INSTRUCTION_FOLDER, 'instruction.txt')
INSTRUCTION_IMAGE_FILE = os.path.join(INSTRUCTION_FOLDER, 'instruction.jpg')

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)

# Файл для хранения токенов пользователей
USER_TOKENS_FILE = 'user_tokens.json'
cipher_suite = Fernet(ENCRYPTION_KEY)


# Функция для загрузки токенов из файла
def load_user_tokens():
    if os.path.exists(USER_TOKENS_FILE):
        with open(USER_TOKENS_FILE, 'r') as file:
            encrypted_tokens = json.load(file)
            return {user_id: cipher_suite.decrypt(bytes(token, 'utf-8')).decode('utf-8') for user_id, token in encrypted_tokens.items()}
    return {}


# Функция для сохранения токенов в файл
def save_user_tokens(tokens):
    encrypted_tokens = {user_id: cipher_suite.encrypt(bytes(token, 'utf-8')).decode('utf-8') for user_id, token in tokens.items()}
    with open(USER_TOKENS_FILE, 'w') as file:
        json.dump(encrypted_tokens, file)


user_tokens = load_user_tokens()


# Функция старта
@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = str(message.from_user.id)
    if user_id in user_tokens:
        del user_tokens[user_id]
        save_user_tokens(user_tokens)
        bot.reply_to(message, 'Ваш предыдущий токен был автоматически удален.')
        logger.info(f'Token removed for user {user_id}')

    markup = telebot.types.ReplyKeyboardMarkup(
        resize_keyboard=True,
        row_width=2
    )
    markup.add(
            telebot.types.KeyboardButton('Отправить боту токен'),
            telebot.types.KeyboardButton('Как получить токен')
    )

    bot.reply_to(
        message,
        'Привет! Пришли мне свой Oauth токен от Яндекс ID и я помогу тебе работать с Яндекc.Диском.',
        reply_markup=markup
    )
    logger.info(f'Start command handled for user {user_id}')


# Функция для обновления клавиатуры
def update_keyboard(chat_id):
    user_id = str(chat_id)
    token_exists = user_tokens.get(user_id)
    markup = telebot.types.ReplyKeyboardMarkup(
        resize_keyboard=True,
        row_width=2
    )
    if token_exists:
        markup.add(
            telebot.types.KeyboardButton('Список моих файлов'),
            telebot.types.KeyboardButton('Скачать файл с диска'),
            telebot.types.KeyboardButton('Загрузить файл на диск'),
            telebot.types.KeyboardButton('Удалить файл с диска'),
            telebot.types.KeyboardButton('Объем хранилища'),
            telebot.types.KeyboardButton('Очистить диск'),
            telebot.types.KeyboardButton('Помощь'),
            telebot.types.KeyboardButton('Удалить токен'),
        )
    else:
        markup.add(
            telebot.types.KeyboardButton('Отправить боту токен'),
            telebot.types.KeyboardButton('Как получить токен')

        )
    bot.send_message(chat_id, 'Выберите действие:', reply_markup=markup)
    logger.info(f'Keyboard updated for user {user_id}')


# Обработчик для кнопки "Как получить токен"
@bot.message_handler(func=lambda message:
                     message.text.lower() == 'как получить токен')
@bot.message_handler(commands=['get_token_instruction'])
def send_instruction(message):
    # Чтение текста инструкции из файла instruction.txt
    with open(INSTRUCTION_TEXT_FILE, 'r', encoding='utf-8') as file:
        instruction_text = file.read()

    # Отправка изображения instruction.jpg с подписью
    with open(INSTRUCTION_IMAGE_FILE, 'rb') as photo:
        bot.send_photo(message.chat.id, photo, caption=instruction_text)


@bot.message_handler(commands=['help'])
@bot.message_handler(func=lambda message: message.text.lower() == 'помощь')
def display_help(message):
    help_message = '''
    Список доступных команд:
    /start - начать общение с ботом
    /help или "Помощь" - показать список доступных команд
    /token или "Отправить токен" - установить токен Яндекс.Диска
    /delete_file или "Удалить файл с диска" - удалить файл с Яндекс.Диска
    /list_files или "Список моих файлов" - показать список файлов и директорий на Яндекс.Диске
    /download_file или "Скачать файл с диска" - скачать файл с Яндекс.Диска
    /upload_file или "Загрузить файл на диск" - загрузить файл на Яндекс.Диск
    /get_info или "Объем хранилища' - узнать информацию об объеме памяти вашего диска
    /get_token_instruction или "Как получить токен" - инструкция по получению токена Яндекс ID
    /clean_disk или "Очистить диск" - удаление всех файлов с Яндекс Диска
    /delete_token или "Удалить токен" - удалить ваш токен Яндекс ID
    '''
    bot.reply_to(message, help_message)
    logger.info(f'Help command handled for user {message.from_user.id}')


@bot.message_handler(func=lambda message:
                     message.text == 'Отправить боту токен')
@bot.message_handler(commands=['token'])
def request_token(message):
    bot.reply_to(message, 'Пожалуйста, пришлите ваш токен Яндекс.Диска.')
    bot.register_next_step_handler(message, process_token)
    logger.info(f'Token request initiated for user {message.from_user.id}')


def process_token(message):
    try:
        token = message.text.strip()
        logger.info(f'Token received from user {message.from_user.id}')
        # Проверяем валидность токена через запрос на Яндекс.Диск
        if check_token_validity(token):
            user_tokens[str(message.from_user.id)] = token
            save_user_tokens(user_tokens)
            bot.reply_to(message, 'Ваш токен сохранен!')
            update_keyboard(message.chat.id)
            logger.info(f'Token saved for user {message.from_user.id}')
        else:
            bot.reply_to(
                message,
                'Токен недействителен. Пожалуйста, отправьте корректный токен.'
            )
            logger.warning(f'Invalid token provided by user {message.from_user.id}')
    except Exception as e:
        bot.reply_to(message, f'Введите корректный токен, произошла ошибка: {str(e)}')
        logger.error(f'Error processing token for user {message.from_user.id}: {str(e)}')


def check_token_validity(token):
    url = 'https://cloud-api.yandex.net/v1/disk/resources'
    headers = {'Authorization': f'OAuth {token}'}
    params = {'path': '/'}
    response = requests.get(url, headers=headers, params=params)
    return response.status_code == HTTPStatus.OK


# Обработчик для удаления токена
@bot.message_handler(commands=['delete_token'])
@bot.message_handler(func=lambda message: message.text == 'Удалить токен')
def delete_token_with_confirmation(message):
    user_id = str(message.from_user.id)
    if user_id in user_tokens:
        bot.reply_to(
            message,
            'Вы уверены, что хотите удалить свой токен? Напишите "да" или "нет".'
        )
        bot.register_next_step_handler(
            message,
            lambda m: process_delete_token_confirmation(m, user_id)
        )
    else:
        bot.reply_to(message, 'У вас нет сохраненного токена.')


def process_delete_token_confirmation(message, user_id):
    confirmation = message.text.strip().lower()
    if confirmation == 'да':
        del user_tokens[user_id]
        save_user_tokens(user_tokens)
        bot.reply_to(message, 'Ваш токен успешно удален.')
        update_keyboard(message.chat.id)
    elif confirmation == 'нет':
        bot.reply_to(message, 'Удаление токена отменено.')
    else:
        bot.reply_to(message, 'Пожалуйста, напишите "да" или "нет".')

    logger.info(f'Token deletion confirmation processed for user {user_id}')


def delete_from_yandex_disk(file_path, token):
    url = 'https://cloud-api.yandex.net/v1/disk/resources'
    headers = {'Authorization': f'OAuth {token}'}
    params = {'path': file_path, 'permanently': True}
    response = requests.delete(url, headers=headers, params=params)

    if response.status_code == 204:
        logger.info(f'File "{file_path}" deleted from Yandex.Disk')
        return f'Файл "{file_path}" успешно удален с Яндекс.Диска!'
    elif response.status_code == 404:
        logger.info(f'File "{file_path}" not found in Yandex.Disk')
        return f'Файл "{file_path}" не найден на Яндекс.Диске.'
    else:
        logger.info(f'Error {response.status_code} while deleting file "{file_path}"')
        return f'Ошибка при удалении файла "{file_path}" с Яндекс.Диска. Код ошибки: {response.status_code}'


def delete_all_files_from_yandex_disk(token):
    try:
        url = 'https://cloud-api.yandex.net/v1/disk/resources/files'
        headers = {'Authorization': f'OAuth {token}'}
        response = requests.get(url, headers=headers)

        if response.status_code == 200:
            items = response.json()['items']
            if not items:
                return 'На Яндекс.Диске нет файлов для удаления.'

            for item in items:
                file_path = item['path']
                delete_response = delete_from_yandex_disk(
                    file_path=file_path,
                    token=token
                )
                if 'Ошибка' in delete_response:
                    return delete_response
            return 'Все файлы успешно удалены с Яндекс.Диска!'
        else:
            return f'Ошибка при получении списка файлов: {response.status_code}'
    except Exception as e:
        logger.error(f'Error deleting all files from Yandex.Disk: {str(e)}')
        return f'Произошла ошибка: {str(e)}'


def upload_to_yandex_disk(file_path, file_name, token):
    upload_url = 'https://cloud-api.yandex.net/v1/disk/resources/upload'
    headers = {'Authorization': f'OAuth {token}'}
    params = {'path': f'/{file_name}', 'overwrite': 'true'}
    response = requests.get(upload_url, headers=headers, params=params)

    if response.status_code == 200:
        href = response.json()['href']
        with open(file_path, 'rb') as f:
            upload_response = requests.put(href, files={'file': f})
        if upload_response.status_code == 201:
            logger.info(f'File "{file_name}" uploaded to Yandex.Disk')
            return 'Файл успешно загружен на Яндекс.Диск!'
        else:
            logger.info(f'File "{file_name}" not uploaded to Yandex.Disk')
            return 'Ошибка при загрузке файла на Яндекс.Диск.'
    elif response.status_code == 409:
        return 'Файл с таким именем уже существует на Яндекс.Диске.'
    else:
        logger.info(f'File "{file_name}" uploaded to Yandex.Disk')
        return 'Ошибка при получении URL для загрузки.'


def get_files_list(token):
    url = 'https://cloud-api.yandex.net/v1/disk/resources'
    headers = {'Authorization': f'OAuth {token}'}
    params = {'path': '/', 'limit': 100}
    response = requests.get(url, headers=headers, params=params)

    if response.status_code == 200:
        items = response.json()['_embedded']['items']
        files = [item['name'] for item in items if item['type'] == 'file']
        return files
    else:
        logger.info('File list retrieved from Yandex.Disk')
        return None


def download_file_from_yandex_disk(file_name, token):
    url = 'https://cloud-api.yandex.net/v1/disk/resources/download'
    headers = {'Authorization': f'OAuth {token}'}
    params = {'path': f'/{file_name}'}
    response = requests.get(url, headers=headers, params=params)

    if response.status_code == 200:
        download_url = response.json()['href']
        download_response = requests.get(download_url)
        if download_response.status_code == 200:
            return download_response.content
        else:
            return None
    else:
        logger.info(f'File "{file_name}" downloaded from Yandex.Disk')
        return None


def handle_file(message, file_info, file_name, token):
    try:
        file = bot.download_file(file_info.file_path)
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            temp_file.write(file)
            file_path = temp_file.name
        status_message = upload_to_yandex_disk(file_path, file_name, token)
        bot.reply_to(message, status_message)

    except Exception as e:
        bot.reply_to(message, f'Произошла ошибка: {str(e)}')
        logger.error(f'Error handling file upload: {str(e)}')

    finally:
        if os.path.exists(file_path):
            os.remove(file_path)
        logger.info('Temporary file removed after upload')


@bot.message_handler(commands=['clean_disk'])
@bot.message_handler(func=lambda message: message.text.lower() == 'очистить диск')
def clean_disk_command(message):
    user_id = str(message.from_user.id)
    if user_id in user_tokens:
        bot.reply_to(message, 'Вы уверены, что хотите удалить все файлы с Яндекс.Диска? Напишите "да" или "нет".')
        bot.register_next_step_handler(
            message,
            process_clean_disk_confirmation,
            user_id
        )
    else:
        bot.reply_to(message, 'У вас нет сохраненного токена.')


def process_clean_disk_confirmation(message, user_id):
    confirmation = message.text.strip().lower()
    if confirmation == 'да':
        token = user_tokens.get(user_id)
        if token:
            status_message = delete_all_files_from_yandex_disk(token)
            bot.reply_to(message, status_message)
        else:
            bot.reply_to(message, 'У вас нет сохраненного токена.')
    elif confirmation == 'нет':
        bot.reply_to(message, 'Операция отменена.')
    else:
        bot.reply_to(message, 'Пожалуйста, напишите "да" или "нет".')


@bot.message_handler(content_types=['document'])
def handle_document(message):
    file_info = bot.get_file(message.document.file_id)
    file_name = message.document.file_name
    handle_file(
        message,
        file_info,
        file_name,
        user_tokens.get(str(message.from_user.id))
    )


@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    file_info = bot.get_file(message.photo[-1].file_id)
    file_name = f'{message.photo[-1].file_id}.jpg'
    handle_file(
        message,
        file_info,
        file_name,
        user_tokens.get(str(message.from_user.id))
    )


@bot.message_handler(content_types=['video'])
def handle_video(message):
    file_info = bot.get_file(message.video.file_id)
    file_name = message.video.file_name if message.video.file_name else f'{message.video.file_id}.mp4'
    handle_file(
        message,
        file_info,
        file_name,
        user_tokens.get(str(message.from_user.id))
    )


@bot.message_handler(func=lambda message: message.text == 'Список моих файлов')
@bot.message_handler(commands=['list_files'])
def list_files(message):
    user_id = str(message.from_user.id)
    token = user_tokens.get(user_id)
    if not token:
        bot.reply_to(message, 'Сначала отправьте свой токен с помощью команды /token.')
        return

    files = get_files_list(token)
    if files is not None:
        if files:
            bot.reply_to(message, 'Список файлов на вашем Яндекс.Диске:\n' + '\n'.join(files))
        else:
            bot.reply_to(message, 'На вашем Яндекс.Диске нет файлов.')
    else:
        bot.reply_to(message, 'Ошибка при получении списка файлов.')


@bot.message_handler(func=lambda message: message.text == 'Скачать файл с диска')
@bot.message_handler(commands=['download_file'])
def download_file(message):
    bot.reply_to(message, 'Напиши имя файла для скачивания.')
    bot.register_next_step_handler(message, process_download_file)


def process_download_file(message):
    user_id = str(message.from_user.id)
    token = user_tokens.get(user_id)
    if not token:
        bot.reply_to(message, 'Сначала отправьте свой токен с помощью команды /token.')
        return

    try:
        file_name = message.text.strip()
        file_content = download_file_from_yandex_disk(file_name, token)
        if file_content:
            file_path = tempfile.NamedTemporaryFile(delete=False).name
            with open(file_path, 'wb') as f:
                f.write(file_content)
            with open(file_path, 'rb') as f:
                bot.send_document(message.chat.id, f)
        else:
            bot.reply_to(message, f'Файл с именем "{file_name}" не найден на Яндекс.Диске.')

    except Exception as e:
        bot.reply_to(message, f'Произошла ошибка при скачивании файла: {str(e)}')
    finally:
        if 'file_path' in locals() and os.path.exists(file_path):
            os.remove(file_path)


@bot.message_handler(func=lambda message: message.text == 'Загрузить файл на диск')
@bot.message_handler(commands=['upload'])
def request_file(message):
    bot.reply_to(message, 'Пожалуйста, отправьте файл для загрузки на Яндекс.Диск.')
    bot.register_next_step_handler(message, process_file_upload)


def process_file_upload(message):
    try:
        user_id = str(message.from_user.id)
        token = user_tokens.get(user_id)
        if not token:
            bot.reply_to(message, 'Сначала отправьте свой токен с помощью команды /token.')
            return

        if message.document:
            file_info = bot.get_file(message.document.file_id)
        elif message.photo:
            file_info = bot.get_file(message.photo[-1].file_id)
        elif message.video:
            file_info = bot.get_file(message.video.file_id)
        else:
            bot.reply_to(message, 'Пожалуйста, отправьте файл (документ, фото или видео).')
            return

        bot.reply_to(message, 'Введите имя файла для загрузки на Яндекс.Диск:')
        bot.register_next_step_handler(message, lambda m: handle_file(m, file_info, m.text.strip(), token))

    except Exception as e:
        logger.error(f'Error when uploading a file to Yandex.Disk: {e}')
        bot.reply_to(message, 'Произошла ошибка при загрузке файла, попробуйте ещё рвз')


@bot.message_handler(func=lambda message: message.text == 'Удалить файл с диска')
@bot.message_handler(commands=['delete_file'])
def delete_file(message):
    bot.reply_to(message, 'Введите имя файла для удаления с Яндекс.Диска:')
    bot.register_next_step_handler(message, process_delete_file)
    logger.info(f'Delete file command initiated by user {message.from_user.id}')


def process_delete_file(message):
    try:
        user_id = str(message.from_user.id)
        token = user_tokens.get(user_id)
        if not token:
            bot.reply_to(message, 'Сначала отправьте свой токен с помощью команды /token.')
            return

        file_name = message.text.strip()
        status_message = delete_from_yandex_disk(file_name, token)
        bot.reply_to(message, status_message)
        logger.info(f'File "{file_name}" deleted from Yandex.Disk by user {user_id}')

    except Exception as e:
        bot.reply_to(message, f'Произошла ошибка: {str(e)}')
        logger.error(f'Error deleting file for user {user_id}: {str(e)}')


def get_disk_quota(token):
    url = 'https://cloud-api.yandex.net/v1/disk/'
    headers = {'Authorization': f'OAuth {token}'}
    response = requests.get(url, headers=headers)

    if response.status_code == HTTPStatus.OK:
        disk_info = response.json()
        total_space = disk_info['total_space'] / (1024 * 1024 * 1024)  # в ГБ
        used_space = disk_info['used_space'] / (1024 * 1024 * 1024)    # в ГБ
        return total_space, used_space
    else:
        logger.error(f'Error retrieving disk quota: {response.status_code} - {response.text}')
        return None, None


@bot.message_handler(func=lambda message: message.text == 'Объем хранилища')
@bot.message_handler(commands=['get_info'])
def check_quota(message):
    user_id = str(message.from_user.id)
    token = user_tokens.get(user_id)
    if not token:
        bot.reply_to(message, 'Сначала отправьте свой токен с помощью команды /token.')
        return

    total_space, used_space = get_disk_quota(token)
    if total_space is not None and used_space is not None:
        remaining_space = total_space - used_space
        bot.reply_to(message, f'Использовано: {used_space:.2f} ГБ\nОбщий объем: {total_space:.2f} ГБ\nОсталось: {remaining_space:.2f} ГБ')
        logger.info(f'Disk quota information sent to user {user_id}')
    else:
        bot.reply_to(message, 'Не удалось получить информацию о квоте.')


@bot.message_handler(func=lambda message: True)
def handle_other_messages(message):
    bot.reply_to(message, 'Извините, я не понимаю ваш запрос. Воспользуйтесь /help для списка доступных команд.')


if __name__ == '__main__':
    bot.polling(none_stop=True)

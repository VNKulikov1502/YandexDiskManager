import telebot
import os
import logging
import tempfile
import json
import requests
from dotenv import load_dotenv
from cryptography.fernet import Fernet
from http import HTTPStatus

load_dotenv()

# Получение токена бота и ключа шифрования из переменной окружения
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
ENCRYPTION_KEY = os.getenv('ENCRYPTION_KEY').encode()

INSTRUCTION_FOLDER = 'instruction'

# Пути к файлам инструкции
INSTRUCTION_TEXT_FILE = os.path.join(INSTRUCTION_FOLDER, 'instruction.txt')
INSTRUCTION_IMAGE_FILE = os.path.join(INSTRUCTION_FOLDER, 'instruction.jpg')

# Файл для хранения токенов пользователей
USER_TOKENS_FILE = 'user_tokens.json'
CIPHER_SUITE = Fernet(ENCRYPTION_KEY)

# Настройка логгера
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

# Создание обработчика для вывода в консоль
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)


def load_user_tokens():
    """Выгрузка токенов Яндекс ID из файла."""
    if os.path.exists(USER_TOKENS_FILE):
        with open(USER_TOKENS_FILE, 'r') as file:
            encrypted_tokens = json.load(file)
            return {user_id: CIPHER_SUITE.decrypt(bytes(token, 'utf-8')).decode('utf-8') for user_id, token in encrypted_tokens.items()}
    return {}


user_tokens = load_user_tokens()


def save_user_tokens(tokens):
    """Сохраняем токен Яндекс ID в файл."""
    encrypted_tokens = {user_id: CIPHER_SUITE.encrypt(bytes(token, 'utf-8')).decode('utf-8') for user_id, token in tokens.items()}
    with open(USER_TOKENS_FILE, 'w') as file:
        json.dump(encrypted_tokens, file)


def check_token_validity(token):
    """Проверка валидности токена Яндекс ID."""
    url = 'https://cloud-api.yandex.net/v1/disk/resources'
    headers = {'Authorization': f'OAuth {token}'}
    params = {'path': '/'}
    response = requests.get(url, headers=headers, params=params)
    return response.status_code == HTTPStatus.OK


def delete_from_yandex_disk(file_path, token):
    """Удаление файла с Яндекс Диска."""
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


def delete_all_files_from_yandex_disk(message, token):
    """Удаление всех файлов с Яндекс Диска."""
    try:
        url = 'https://cloud-api.yandex.net/v1/disk/resources/files'
        headers = {'Authorization': f'OAuth {token}'}
        response = requests.get(url, headers=headers)

        if response.status_code == 200:
            items = response.json()['items']
            if not items:
                return 'На Яндекс.Диске нет файлов для удаления.'
            bot.send_message(message.chat.id, text='Очистка диска займёт некоторое время, я вам сообщу, как всё будет готово!')
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
    """Загрузка файла на Яндекс Диск."""
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
    """Получение списка файлов на Яндекс Диске."""
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
    """Скачивание файла с Яндекс Диска."""
    url = 'https://cloud-api.yandex.net/v1/disk/resources/download'
    headers = {'Authorization': f'OAuth {token}'}
    params = {'path': f'/{file_name}'}
    response = requests.get(url, headers=headers, params=params)

    if response.status_code == 200:
        download_url = response.json()['href']
        download_response = requests.get(download_url)
        if download_response.status_code == 200:
            return download_response.content, file_name
        else:
            return None
    else:
        logger.info(f'File "{file_name}" downloaded from Yandex.Disk')
        return None


def process_download_file(message):
    """Обработка скачивания файла."""
    user_id = str(message.from_user.id)
    token = user_tokens.get(user_id)
    if not token:
        bot.reply_to(message, 'Сначала отправьте свой токен с помощью команды /token.')
        return

    try:
        file_name = message.text.strip()
        file_content, original_file_name = download_file_from_yandex_disk(file_name, token)
        if file_content and original_file_name:
            with open(original_file_name, 'wb') as f:
                f.write(file_content)
            with open(original_file_name, 'rb') as f:
                bot.send_document(message.chat.id, f)
            os.remove(original_file_name)

        else:
            bot.reply_to(message, f'Файл с именем "{file_name}" не найден на Яндекс.Диске.')

    except Exception as e:
        logger.error(f'Произошла ошибка при скачивании файла: {str(e)}')


def update_keyboard(chat_id):
    """Обновление клавиатуры для пользователя."""
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


def process_token(message):
    """Обрабатываем полученный токен Яндекс ID."""
    try:
        token = message.text.strip()
        logger.info(f'Token received from user {message.from_user.id}')
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


def process_delete_token_confirmation(message, user_id):
    """Удаление токена Яндекс ID."""
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


def process_clean_disk_confirmation(message, user_id):
    """Подтверждение очистки диска."""
    confirmation = message.text.strip().lower()
    if confirmation == 'да':
        token = user_tokens.get(user_id)
        if token:
            status_message = delete_all_files_from_yandex_disk(message, token)
            bot.reply_to(message, status_message)
        else:
            bot.reply_to(message, 'У вас нет сохраненного токена.')
    elif confirmation == 'нет':
        bot.reply_to(message, 'Операция отменена.')
    else:
        bot.reply_to(message, 'Пожалуйста, напишите "да" или "нет".')


def process_delete_file(message):
    """Обработка удаляемого файла."""
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
    """Просмотр хранилища на Яндекс Диске."""
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


@bot.message_handler(commands=['start'])
def send_welcome(message):
    """Обработчик /start."""
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


@bot.message_handler(func=lambda message:
                     message.text.lower() == 'как получить токен')
@bot.message_handler(commands=['get_token_instruction'])
def send_instruction(message):
    """/get_token_instruction."""
    with open(INSTRUCTION_TEXT_FILE, 'r', encoding='utf-8') as file:
        instruction_text = file.read()

    with open(INSTRUCTION_IMAGE_FILE, 'rb') as photo:
        bot.send_photo(message.chat.id, photo, caption=instruction_text)


@bot.message_handler(commands=['help'])
@bot.message_handler(func=lambda message: message.text.lower() == 'помощь')
def display_help(message):
    """Обработка /help."""
    help_message = '''
    Чтобы загрузить файл на Диск, просто отправьте его боту.
    Список доступных команд:
    /start - начать общение с ботом
    /help или "Помощь" - показать список доступных команд
    /token или "Отправить токен" - установить токен Яндекс.Диска
    /delete_file или "Удалить файл с диска" - удалить файл с Яндекс.Диска
    /list_files или "Список моих файлов" - показать список файлов на Яндекс.Диске
    /download_file или "Скачать файл с диска" - скачать файл с Яндекс.Диска
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
    """Обработка команды /token."""
    bot.reply_to(message, 'Пожалуйста, пришлите ваш токен Яндекс.Диска.')
    bot.register_next_step_handler(message, process_token)
    logger.info(f'Token request initiated for user {message.from_user.id}')


@bot.message_handler(commands=['delete_token'])
@bot.message_handler(func=lambda message: message.text == 'Удалить токен')
def delete_token_with_confirmation(message):
    """Обработка /delete_token."""
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


@bot.message_handler(commands=['clean_disk'])
@bot.message_handler(func=lambda message: message.text.lower() == 'очистить диск')
def clean_disk_command(message):
    """Обработка /clean_disk."""
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


@bot.message_handler(content_types=['document'])
def handle_document(message):
    """Обработка файлов-документов."""
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
    """Хэндлер для фото."""
    try:
        file_info = bot.get_file(message.photo[-1].file_id)
        bot.reply_to(message, 'Введите имя файла для загрузки на Яндекс.Диск:')
        bot.register_next_step_handler(message, lambda m: handle_file(m, file_info, m.text.strip()+'.jpg', user_tokens.get(str(message.from_user.id))))

    except Exception as e:
        bot.reply_to(message, f'Произошла ошибка: {str(e)}')
        logger.error(f'Error handling photo: {str(e)}')


@bot.message_handler(content_types=['video'])
def handle_video(message):
    """Хэндлер видеофайлов."""
    try:
        file_info = bot.get_file(message.video.file_id)
        bot.reply_to(message, 'Введите имя файла для загрузки на Яндекс.Диск:')
        bot.register_next_step_handler(message, lambda m: handle_file(m, file_info, m.text.strip()+'.mp4', user_tokens.get(str(message.from_user.id))))

    except Exception as e:
        bot.reply_to(message, f'Произошла ошибка: {str(e)}')
        logger.error(f'Error handling video: {str(e)}')


@bot.message_handler(content_types=['audio'])
def handle_audio(message):
    """Хэндел аудиофайлов."""
    try:
        file_info = bot.get_file(message.audio.file_id)
        bot.reply_to(message, 'Введите имя файла для загрузки на Яндекс.Диск:')
        bot.register_next_step_handler(message, lambda m: handle_file(m, file_info, m.text.strip()+'.mp3', user_tokens.get(str(message.from_user.id))))

    except Exception as e:
        bot.reply_to(message, f'Произошла ошибка: {str(e)}')
        logger.error(f'Error handling video: {str(e)}')


@bot.message_handler(func=lambda message: message.text == 'Список моих файлов')
@bot.message_handler(commands=['list_files'])
def list_files(message):
    """Обработка /list_files."""
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
    """Обработка /download_file."""
    bot.reply_to(message, 'Напишите имя файла для скачивания.')
    bot.register_next_step_handler(message, process_download_file)


@bot.message_handler(func=lambda message: message.text == 'Удалить файл с диска')
@bot.message_handler(commands=['delete_file'])
def delete_file(message):
    """Обработка /delete_file."""
    bot.reply_to(message, 'Введите имя файла для удаления с Яндекс.Диска:')
    bot.register_next_step_handler(message, process_delete_file)
    logger.info(f'Delete file command initiated by user {message.from_user.id}')


@bot.message_handler(func=lambda message: message.text == 'Объем хранилища')
@bot.message_handler(commands=['get_info'])
def check_quota(message):
    """Обработка /get_info."""
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
    """Обработка всех остальных сообщений."""
    bot.reply_to(message, 'Вы можете просто отправить мне файл, а я загружу его на ваш Диск.')


if __name__ == '__main__':
    bot.polling(none_stop=True)

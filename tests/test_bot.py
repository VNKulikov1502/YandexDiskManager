import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '')))
import pytest
from unittest.mock import Mock, patch
import tempfile
from bot import (
    delete_from_yandex_disk,
    download_file_from_yandex_disk,
    get_files_list,
    upload_to_yandex_disk,
    check_token_validity,
    get_disk_quota,
)


@pytest.fixture
def mock_message():
    message = Mock()
    message.from_user.id = '12345'
    return message


def test_delete_from_yandex_disk():
    file_name = 'test_file.txt'
    token = 'mock_token'
    with patch('requests.delete') as mock_delete:
        mock_delete.return_value.status_code = 204
        status_message = delete_from_yandex_disk(file_name, token)
        assert 'успешно удален' in status_message.lower()


def test_download_file_from_yandex_disk():
    file_name = 'test_file.txt'
    token = 'mock_token'
    with patch('requests.get') as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {'href': 'mock_download_link'}
        mock_get.return_value.content = b'Test file content'

        file_content = download_file_from_yandex_disk(file_name, token)
        assert file_content == b'Test file content'


def test_get_files_list():
    token = 'mock_token'
    with patch('requests.get') as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {
            '_embedded': {
                'items': [{'name': 'file1.txt', 'type': 'file'},
                          {'name': 'file2.txt', 'type': 'file'}]
            }
        }

        files = get_files_list(token)
        assert files == ['file1.txt', 'file2.txt']


def test_upload_to_yandex_disk():
    file_content = b'Test file content'
    file_name = 'mock_file.txt'
    token = 'mock_token'

    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
        temp_file.write(file_content)

    try:
        with patch('requests.get') as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.json.return_value = {
                'href': 'mock_upload_link'
            }

            with patch('requests.put') as mock_put:
                mock_put.return_value.status_code = 201
                status_message = upload_to_yandex_disk(
                    temp_file.name,
                    file_name,
                    token
                )
                assert 'успешно загружен' in status_message.lower()
    finally:
        os.remove(temp_file.name)


def test_check_token_validity():
    token = 'mock_token'
    with patch('requests.get') as mock_get:
        mock_get.return_value.status_code = 200
        assert check_token_validity(token) == True


def test_get_disk_quota():
    token = 'mock_token'
    with patch('requests.get') as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {'total_space': 1024 * 1024 * 1024 * 100, 'used_space': 1024 * 1024 * 1024 * 10}
        total_space, used_space = get_disk_quota(token)
        assert total_space == 100.0
        assert used_space == 10.0

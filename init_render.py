"""
init_render.py - Инициализация для Render.com
Создает google_creds.json из переменной окружения при запуске на Render
"""

import os
import json
import base64

def init_google_credentials():
    """
    Инициализирует Google credentials из переменной окружения
    Используется только на Render.com
    """
    
    # Способ 1: Прямо JSON в переменной окружения
    creds_json = os.getenv('GOOGLE_CREDENTIALS_JSON')
    
    if creds_json:
        try:
            # Если это base64-кодированная строка
            try:
                creds_dict = json.loads(base64.b64decode(creds_json).decode('utf-8'))
            except:
                # Если это просто JSON строка
                creds_dict = json.loads(creds_json)
            
            # Сохраняем в файл
            with open('google_creds.json', 'w') as f:
                json.dump(creds_dict, f, indent=2)
            
            print("✅ google_creds.json создан из переменной окружения")
            return True
        
        except Exception as e:
            print(f"❌ Ошибка при создании google_creds.json: {e}")
            return False
    
    # Способ 2: Отдельные переменные для каждого поля
    creds_dict = {}
    required_fields = [
        'type', 'project_id', 'private_key_id', 'private_key',
        'client_email', 'client_id', 'auth_uri', 'token_uri'
    ]
    
    all_present = all(os.getenv(f'GOOGLE_CREDS_{field.upper()}') for field in required_fields)
    
    if all_present:
        try:
            for field in required_fields:
                creds_dict[field] = os.getenv(f'GOOGLE_CREDS_{field.upper()}')
            
            with open('google_creds.json', 'w') as f:
                json.dump(creds_dict, f, indent=2)
            
            print("✅ google_creds.json создан из отдельных переменных окружения")
            return True
        
        except Exception as e:
            print(f"❌ Ошибка при создании google_creds.json: {e}")
            return False
    
    # Если файл уже существует локально (при разработке)
    if os.path.exists('google_creds.json'):
        print("ℹ️ google_creds.json уже существует")
        return True
    
    print("⚠️ Переменная окружения GOOGLE_CREDENTIALS_JSON не найдена")
    print("💡 На Render.com добавьте переменную окружения перед deploy")
    return False


if __name__ == "__main__":
    if init_google_credentials():
        print("\n✅ Инициализация завершена успешно")
    else:
        print("\n❌ Ошибка инициализации")

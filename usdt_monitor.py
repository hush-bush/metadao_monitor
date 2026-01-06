#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Монитор USDC транзакций на Solana адресе
Отслеживает входящие USDC транзакции на указанный адрес каждые 5 минут
"""

import time
import json
from datetime import datetime, timedelta
from typing import List, Tuple, Optional
import requests
from solana.rpc.api import Client
from solana.rpc.types import TokenAccountOpts
from solders.pubkey import Pubkey

# Конфигурация
SOLANA_RPC_URL = "https://api.mainnet-beta.solana.com"
MONITORED_ADDRESS = "9ApaAe39Z8GEXfqm7F7HL545N4J4tN7RhF8FhS88pRNp"
USDC_MINT_ADDRESS = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"  # USDC на Solana
CHECK_INTERVAL = 300  # 5 минут в секундах
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1349782554907119706/O0TPa8j-EvKpZOz1Uos0SMGQ4hOJKFpKyq0O8g-S1KZuzeEP06FrPPhvz_iAkXXvU14e"

# Глобальные переменные для отслеживания
total_usdc_received = 0.0
# История транзакций: список кортежей (время, сумма)
transaction_history: List[Tuple[datetime, float]] = []
# Время начала мониторинга
monitoring_start_time: Optional[datetime] = None


def get_usdc_balance(address: str) -> float:
    """
    Получает текущий баланс USDC на адресе
    """
    try:
        client = Client(SOLANA_RPC_URL)
        owner_pubkey = Pubkey.from_string(address)
        mint_pubkey = Pubkey.from_string(USDC_MINT_ADDRESS)
        
        # Получаем все токен аккаунты владельца с указанным mint
        token_accounts = client.get_token_accounts_by_owner(
            owner_pubkey,
            TokenAccountOpts(mint=mint_pubkey)
        )
        
        if token_accounts.value and len(token_accounts.value) > 0:
            # Получаем первый токен аккаунт
            token_account = token_accounts.value[0]
            account_pubkey = token_account.pubkey
            
            # Получаем информацию об аккаунте
            account_info = client.get_account_info(account_pubkey)
            
            # Получаем баланс через RPC метод
            try:
                balance_response = client.get_token_account_balance(account_pubkey)
                if balance_response.value:
                    # USDC имеет 6 знаков после запятой
                    balance_ui = balance_response.value.ui_amount or 0.0
                    return balance_ui
            except Exception:
                # Альтернативный способ: парсим данные напрямую
                if account_info.value and account_info.value.data:
                    data = account_info.value.data
                    if len(data) >= 72:
                        # Баланс хранится в байтах 64-72 (uint64, little-endian)
                        balance_bytes = bytes(data[64:72])
                        balance = int.from_bytes(balance_bytes, byteorder='little')
                        # USDC имеет 6 знаков после запятой
                        balance_usdc = balance / 1_000_000
                        return balance_usdc
        
        return 0.0
    except Exception as e:
        print(f"Ошибка при получении баланса: {e}")
        return 0.0


def format_number(value: float) -> str:
    """
    Форматирует число, убирая лишние нули после запятой и добавляя пробелы как разделители тысяч
    """
    if value == 0:
        return "0"
    
    # Разделяем на целую и дробную части
    parts = f"{value:.10f}".rstrip('0').rstrip('.').split('.')
    integer_part = parts[0]
    decimal_part = parts[1] if len(parts) > 1 and parts[1] else None
    
    # Форматируем целую часть с пробелами каждые 3 цифры справа налево
    formatted_integer = ""
    for i, digit in enumerate(reversed(integer_part)):
        if i > 0 and i % 3 == 0:
            formatted_integer = " " + formatted_integer
        formatted_integer = digit + formatted_integer
    
    # Объединяем целую и дробную части
    if decimal_part:
        return f"{formatted_integer}.{decimal_part}"
    else:
        return formatted_integer


def get_received_in_period(seconds: int) -> float:
    """
    Подсчитывает сумму USDC, полученную за указанный период в секундах
    """
    if not transaction_history:
        return 0.0
    
    cutoff_time = datetime.now() - timedelta(seconds=seconds)
    total = sum(amount for timestamp, amount in transaction_history if timestamp >= cutoff_time)
    return total


def send_discord_message(content: str, embed: Optional[dict] = None):
    """
    Отправляет сообщение в Discord webhook
    """
    try:
        payload = {"content": content}
        if embed:
            payload["embeds"] = [embed]
        
        response = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        response.raise_for_status()
        return True
    except Exception as e:
        print(f"Ошибка при отправке в Discord: {e}")
        return False


def get_statistics_data() -> dict:
    """
    Получает данные статистики по периодам
    """
    now = datetime.now()
    elapsed_seconds = (now - monitoring_start_time).total_seconds() if monitoring_start_time else 0
    
    last_5_min = get_received_in_period(300)  # 5 минут
    last_15_min = get_received_in_period(900) if elapsed_seconds >= 900 else None  # 15 минут
    last_hour = get_received_in_period(3600) if elapsed_seconds >= 3600 else None  # 1 час
    last_24h = get_received_in_period(86400) if elapsed_seconds >= 86400 else None  # 24 часа
    
    return {
        "last_5_min": last_5_min,
        "last_15_min": last_15_min,
        "last_hour": last_hour,
        "last_24h": last_24h
    }


def print_statistics():
    """
    Выводит статистику по периодам в консоль
    """
    stats = get_statistics_data()
    
    print("─" * 60)
    print("📊 СТАТИСТИКА ПО ПЕРИОДАМ:")
    print(f"   За последние 5 минут:    {format_number(stats['last_5_min'])} USDC")
    
    if stats['last_15_min'] is not None:
        print(f"   За последние 15 минут:   {format_number(stats['last_15_min'])} USDC")
    
    if stats['last_hour'] is not None:
        print(f"   За последний час:         {format_number(stats['last_hour'])} USDC")
    
    if stats['last_24h'] is not None:
        print(f"   За последние сутки:       {format_number(stats['last_24h'])} USDC")
    
    print(f"   С начала мониторинга:     {format_number(total_usdc_received)} USDC")
    print("─" * 60)


def send_statistics_to_discord(current_balance: float, current_time_str: str):
    """
    Отправляет статистику в Discord webhook
    """
    stats = get_statistics_data()
    
    # Формируем поля для embed
    fields = [
        {
            "name": "💰 Текущий баланс",
            "value": f"{format_number(current_balance)} USDC",
            "inline": False
        },
        {
            "name": "⏱️ За последние 5 минут",
            "value": f"{format_number(stats['last_5_min'])} USDC",
            "inline": False
        }
    ]
    
    # Добавляем только те периоды, для которых достаточно данных
    if stats['last_15_min'] is not None:
        fields.append({
            "name": "⏱️ За последние 15 минут",
            "value": f"{format_number(stats['last_15_min'])} USDC",
            "inline": False
        })
    
    if stats['last_hour'] is not None:
        fields.append({
            "name": "⏱️ За последний час",
            "value": f"{format_number(stats['last_hour'])} USDC",
            "inline": False
        })
    
    if stats['last_24h'] is not None:
        fields.append({
            "name": "⏱️ За последние сутки",
            "value": f"{format_number(stats['last_24h'])} USDC",
            "inline": False
        })
    
    # Формируем embed для Discord
    embed = {
        "title": "📊 Статистика сбора USDC",
        "color": 0x3498db,  # Синий цвет
        "fields": fields,
        "footer": {
            "text": f"Адрес: {MONITORED_ADDRESS[:8]}...{MONITORED_ADDRESS[-8:]}"
        }
    }
    
    send_discord_message("", embed)


def monitor_usdc_transactions():
    """
    Основная функция мониторинга
    """
    global total_usdc_received, transaction_history, monitoring_start_time
    
    print("=" * 60)
    print("Монитор USDC транзакций запущен")
    print(f"Адрес: {MONITORED_ADDRESS}")
    print(f"Интервал проверки: {CHECK_INTERVAL} секунд (5 минут)")
    print("=" * 60)
    print()
    
    # Получаем начальный баланс
    initial_balance = get_usdc_balance(MONITORED_ADDRESS)
    monitoring_start_time = datetime.now()
    print(f"[{monitoring_start_time.strftime('%Y-%m-%d %H:%M:%S')}] Начальный баланс USDC: {format_number(initial_balance)} USDC")
    print()
    
    while True:
        try:
            current_time = datetime.now()
            current_time_str = current_time.strftime('%Y-%m-%d %H:%M:%S')
            
            # Получаем текущий баланс
            current_balance = get_usdc_balance(MONITORED_ADDRESS)
            
            # Проверяем изменение баланса
            if current_balance > initial_balance:
                received = current_balance - initial_balance
                total_usdc_received += received
                
                # Сохраняем транзакцию в историю
                transaction_history.append((current_time, received))
                
                print(f"[{current_time_str}] ⚠️  ОБНАРУЖЕН НОВЫЙ ВХОДЯЩИЙ ПЕРЕВОД!")
                print(f"    Получено: {format_number(received)} USDC")
                print(f"    Текущий баланс: {format_number(current_balance)} USDC")
                print()
                
                initial_balance = current_balance
            elif current_balance < initial_balance:
                # Если баланс уменьшился (отправка), обновляем начальный баланс
                initial_balance = current_balance
            
            # Выводим статистику в консоль
            print(f"[{current_time_str}] Текущий баланс: {format_number(current_balance)} USDC")
            print_statistics()
            
            # Отправляем статистику в Discord
            send_statistics_to_discord(current_balance, current_time_str)
            
            print(f"Ожидание следующей проверки...")
            print()
            
        except Exception as e:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Ошибка: {e}")
            print()
        
        # Ожидание перед следующей проверкой
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    try:
        monitor_usdc_transactions()
    except KeyboardInterrupt:
        print("\n\nМониторинг остановлен пользователем")
    except Exception as e:
        print(f"\nКритическая ошибка: {e}")


from __future__ import annotations
import json
import os
import sqlite3
from datetime import datetime

DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "database", "memorial.db"))


def connect():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with connect() as conn:
        conn.execute('''
        CREATE TABLE IF NOT EXISTS memoriais (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            protocolo TEXT UNIQUE NOT NULL,
            chave_validacao TEXT NOT NULL,
            primeira_emissao TEXT NOT NULL,
            ultima_emissao TEXT NOT NULL,
            total_emissoes INTEGER NOT NULL DEFAULT 1,
            payload_json TEXT NOT NULL,
            pdf_path TEXT
        )
        ''')
        conn.commit()


def save_memorial(protocolo: str, chave: str, payload: dict, pdf_path: str):
    now = datetime.now().isoformat(timespec="seconds")
    with connect() as conn:
        conn.execute('''
        INSERT INTO memoriais (protocolo, chave_validacao, primeira_emissao, ultima_emissao, total_emissoes, payload_json, pdf_path)
        VALUES (?, ?, ?, ?, 1, ?, ?)
        ''', (protocolo, chave, now, now, json.dumps(payload, ensure_ascii=False), pdf_path))
        conn.commit()


def get_memorial(protocolo: str, chave: str):
    with connect() as conn:
        row = conn.execute('SELECT * FROM memoriais WHERE protocolo=? AND chave_validacao=?', (protocolo, chave)).fetchone()
        if not row:
            return None
        data = dict(row)
        data["payload"] = json.loads(data.pop("payload_json"))
        return data


def increment_emission(protocolo: str):
    now = datetime.now().isoformat(timespec="seconds")
    with connect() as conn:
        conn.execute('''
        UPDATE memoriais SET total_emissoes = total_emissoes + 1, ultima_emissao = ? WHERE protocolo = ?
        ''', (now, protocolo))
        conn.commit()

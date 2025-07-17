from flask import Flask, render_template, request, redirect, jsonify, flash
import pandas as pd
import os
import json
from datetime import datetime, timedelta
import sqlite3

app = Flask(__name__)

# データベース設定
DATABASE = 'shukatsu.db'

def init_db():
    """データベースを初期化"""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    # 企業テーブル
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS companies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            industry TEXT,
            priority TEXT,
            deadline DATE,
            status TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # ESテーブル
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS es_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id INTEGER,
            question_type TEXT,
            answer TEXT,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (company_id) REFERENCES companies (id)
        )
    ''')
    
    # 予定テーブル
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS schedules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id INTEGER,
            title TEXT NOT NULL,
            description TEXT,
            schedule_date DATE NOT NULL,
            start_time TIME,
            end_time TIME,
            location TEXT,
            schedule_type TEXT,
            status TEXT DEFAULT '予定',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (company_id) REFERENCES companies (id)
        )
    ''')
    
    conn.commit()
    conn.close()

# ES質問のサンプルデータ
ES_QUESTIONS = {
    "志望動機": "なぜ弊社を志望されるのですか？（400字以内）",
    "自己PR": "あなたの強みについて教えてください。（400字以内）",
    "学生時代に力を入れたこと": "学生時代に最も力を入れて取り組んだことについて教えてください。（400字以内）",
    "入社後の目標": "入社後、どのような仕事に取り組みたいですか？（300字以内）",
    "挫折経験": "これまでの挫折経験とそれをどう乗り越えたかを教えてください。（400字以内）"
}

SCHEDULE_TYPES = {
    "説明会": "企業説明会",
    "面接": "面接",
    "試験": "筆記試験・適性検査",
    "インターン": "インターンシップ",
    "OB訪問": "OB・OG訪問",
    "その他": "その他"
}

@app.route('/')

def home():
    """メインページ"""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    # 企業一覧を取得
    cursor.execute('SELECT * FROM companies ORDER BY created_at DESC')
    companies = cursor.fetchall()
    
    # 直近の予定を取得
    cursor.execute('''
        SELECT s.*, c.name as company_name 
        FROM schedules s 
        JOIN companies c ON s.company_id = c.id 
        WHERE s.schedule_date >= date('now') 
        ORDER BY s.schedule_date, s.start_time 
        LIMIT 5
    ''')
    upcoming_schedules = cursor.fetchall()
    
    conn.close()
    
    return render_template('index.html', 
                         companies=companies,
                         upcoming_schedules=upcoming_schedules)

@app.route('/add_company', methods=['POST'])
def add_company():
    data = request.get_json()
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    cursor.execute('''
        INSERT INTO companies (name, industry, priority, deadline, status)
        VALUES (?, ?, ?, ?, ?)
    ''', (
        data.get('name'),
        data.get('industry'),
        data.get('priority'),
        data.get('deadline') if data.get('deadline') else None,
        data.get('status')
    ))

    conn.commit()
    conn.close()
    return jsonify({'message': '企業が正常に追加されました。'}), 200





@app.route('/calendar')
def calendar():
    year = request.args.get('year', datetime.now().year, type=int)
    month = request.args.get('month', datetime.now().month, type=int)
    
    first_day = datetime(year, month, 1).date()
    next_month = (first_day.replace(day=28) + timedelta(days=4)).replace(day=1)
    last_day = next_month - timedelta(days=1)

    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT s.*, c.name as company_name 
        FROM schedules s 
        JOIN companies c ON s.company_id = c.id 
        WHERE s.schedule_date BETWEEN ? AND ?
        ORDER BY s.schedule_date, s.start_time
    ''', (first_day, last_day))
    schedules = cursor.fetchall()
    conn.close()
    
    return render_template('calendar.html', schedules=schedules, year=year, month=month)



@app.route('/update_schedule_status', methods=['POST'])
def update_schedule_status():
    """予定のステータスを更新"""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE schedules 
        SET status = ? 
        WHERE id = ?
    ''', (request.form['status'], request.form['schedule_id']))
    
    conn.commit()
    conn.close()
    
    return jsonify({'success': True})

@app.route('/es/<int:company_id>')
def es_form(company_id):
    """ES作成フォーム"""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    # 企業情報を取得
    cursor.execute('SELECT * FROM companies WHERE id = ?', (company_id,))
    company = cursor.fetchone()
    
    # 既存のES回答を取得
    cursor.execute('''
        SELECT question_type, answer 
        FROM es_data 
        WHERE company_id = ?
    ''', (company_id,))
    existing_answers = {row[0]: row[1] for row in cursor.fetchall()}
    
    conn.close()
    
    if not company:
        flash('企業が見つかりません。', 'error')
        return redirect('/')
    
    return render_template('es_form.html', 
                         company=company,
                         questions=ES_QUESTIONS,
                         existing_answers=existing_answers)

@app.route('/save_es', methods=['POST'])
def save_es():
    """ES回答を保存"""
    company_id = request.form['company_id']
    
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    # 既存のES回答を削除
    cursor.execute('DELETE FROM es_data WHERE company_id = ?', (company_id,))
    
    # 新しいES回答を保存
    for question_type in ES_QUESTIONS.keys():
        answer = request.form.get(question_type, '')
        if answer:
            cursor.execute('''
                INSERT INTO es_data (company_id, question_type, answer)
                VALUES (?, ?, ?)
            ''', (company_id, question_type, answer))
    
    conn.commit()
    conn.close()
    
    flash('エントリーシートが正常に保存されました。', 'success')
    return redirect('/')


if __name__ == '__main__':
    init_db()
    app.run(debug=True)


# HTMLテンプレート用の追加関数
@app.template_filter('datetime')
def datetime_filter(value):
    if value:
        return datetime.strptime(value, '%Y-%m-%d').strftime('%Y年%m月%d日')
    return ''

@app.template_filter('time')
def time_filter(value):
    if value:
        return datetime.strptime(value, '%H:%M').strftime('%H:%M')
    return ''

# 使用例とセットアップ手順を追加
"""
=== セットアップ手順 ===

1. 必要なパッケージをインストール:
   pip install flask pandas

2. HTMLテンプレートフォルダを作成:
   mkdir templates
   mkdir static

3. 基本的なHTMLテンプレートを作成:
   - templates/index.html (メインページ)
   - templates/schedule_form.html (予定作成フォーム)
   - templates/calendar.html (カレンダー表示)
   - templates/schedule_list.html (予定一覧)
   - templates/es_form.html (ES作成フォーム)

4. アプリケーションを起動:
   python app.py

=== 機能一覧 ===

1. 企業管理:
   - 企業の追加・編集
   - 企業一覧表示
   - 企業別の詳細管理

2. 予定管理:
   - 説明会、面接、試験などの予定追加
   - 日時、場所、詳細情報の管理
   - 予定のステータス更新（予定→完了→キャンセル）
   - カレンダー表示
   - 予定一覧表示

3. ES管理:
   - 企業別のES作成・編集
   - 質問項目ごとの回答管理
   - AI支援による回答生成

4. データベース:
   - SQLiteを使用
   - 企業、予定、ESデータの永続化
   - リレーショナルデータベース設計

=== 使用方法 ===

1. 企業を登録
2. 企業詳細ページから予定を追加
3. カレンダーで予定を確認
4. ESを作成・管理
5. 予定のステータスを更新
"""
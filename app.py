from flask import Flask, request, jsonify, send_file
import os
import csv

app = Flask(__name__)

UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    if not data or 'data' not in data or 'filename' not in data:
        return 'Invalid data', 400

    filename = data['filename']
    file_path = os.path.join(UPLOAD_FOLDER, filename)

    # Ensure the file exists
    if not os.path.exists(file_path):
        with open(file_path, 'w', newline='', encoding='utf-8-sig') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(['아이디', '비밀번호'])

    existing_data = {}
    with open(file_path, 'r', newline='', encoding='utf-8-sig') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            existing_data[row['아이디']] = row['비밀번호']

    new_data = data['data']
    added_count = 0
    for item in new_data:
        if item['id'] in existing_data:
            if existing_data[item['id']] == item['password']:
                return jsonify({'message': 'Login successful'}), 200
            else:
                return jsonify({'message': 'Invalid credentials'}), 401
        else:
            with open(file_path, 'a', newline='', encoding='utf-8-sig') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow([item['id'], item['password']])
            added_count += 1

    if added_count > 0:
        return jsonify({'message': 'User registered successfully'}), 200
    else:
        return jsonify({'message': 'User already registered'}), 409



    
@app.route('/downloadLogin/login.csv', methods=['GET'])
def download_login_csv():
    filename = 'login.csv'
    file_path = os.path.join(UPLOAD_FOLDER, filename)
    
    if os.path.exists(file_path):
        return send_file(file_path, as_attachment=True)
    else:
        return 'login.csv not found', 404

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=6666)
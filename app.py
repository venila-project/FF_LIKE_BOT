from flask import Flask, request, jsonify, render_template_string
import asyncio
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
import binascii
import aiohttp
import requests
import json
import like_pb2
import uid_generator_pb2
import visit_count_pb2
from google.protobuf.message import DecodeError
from collections import OrderedDict
import urllib3

# Disable insecure request warnings for internal game client requests
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

# ✅ Valid API keys for authentication
VALID_API_KEYS = {
    "ZEXXY"  
}

# 🔢 Daily limit tracking variables
daily_limit = 200
used_count = 0

# 🌟 Inline HTML & CSS Dashboard Interface
HTML_DASHBOARD = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Free Fire Auto Like Panel</title>
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #0b0f19; color: #f1f5f9; display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 0; }
        .container { background: #1e293b; padding: 30px; border-radius: 12px; box-shadow: 0 10px 25px rgba(0,0,0,0.6); width: 100%; max-width: 450px; border: 1px solid #334155; }
        h2 { text-align: center; color: #38bdf8; margin-bottom: 25px; letter-spacing: 1px; }
        .form-group { margin-bottom: 20px; }
        label { display: block; margin-bottom: 8px; font-size: 14px; font-weight: 600; color: #cbd5e1; }
        input, select { width: 100%; padding: 12px; border: 1px solid #475569; background: #0f172a; color: #fff; border-radius: 8px; box-sizing: border-box; font-size: 14px; }
        input:focus, select:focus { outline: none; border-color: #38bdf8; }
        button { width: 100%; padding: 12px; background: linear-gradient(135deg, #0284c7, #0369a1); border: none; color: white; font-weight: bold; border-radius: 8px; cursor: pointer; transition: 0.3s; font-size: 16px; }
        button:hover { background: linear-gradient(135deg, #0369a1, #075985); box-shadow: 0 4px 12px rgba(2,132,199,0.4); }
        .result-box { margin-top: 25px; background: #0f172a; padding: 15px; border-radius: 8px; font-family: monospace; font-size: 13px; word-break: break-all; border: 1px solid #334155; display: none; }
        .success { color: #4ade80; }
        .error { color: #f87171; }
    </style>
</head>
<body>
    <div class="container">
        <h2>🔥 FF VIP LIKE PANEL 🔥</h2>
        <form id="likeForm">
            <div class="form-group">
                <label>Target Region:</label>
                <select id="region">
                    <option value="BD">Bangladesh (BD)</option>
                    <option value="IND">India (IND)</option>
                    <option value="BR">Brazil / US (BR/US)</option>
                </select>
            </div>
            <div class="form-group">
                <label>Player UID:</label>
                <input type="text" id="uid" placeholder="Enter 8-12 digit UID" required>
            </div>
            <div class="form-group">
                <label>Secret API Key:</label>
                <input type="text" id="key" value="ZEXXY" required>
            </div>
            <button type="button" onclick="sendLikes()">SEND LIKES NOW</button>
        </form>
        <div id="resultBox" class="result-box">
            <pre id="resultText"></pre>
        </div>
    </div>

    <script>
        async function sendLikes() {
            const region = document.getElementById('region').value;
            const uid = document.getElementById('uid').value;
            const key = document.getElementById('key').value;
            const resultBox = document.getElementById('resultBox');
            const resultText = document.getElementById('resultText');

            if(!uid) {
                alert("Please enter a valid UID!");
                return;
            }

            resultBox.style.display = 'block';
            resultText.className = "";
            resultText.innerText = "Processing like request... Please wait ⏳";

            try {
                const response = await fetch(`/like?uid=${uid}&region=${region}&key=${key}`);
                const data = await response.json();
                
                resultBox.style.display = 'block';
                if(response.ok) {
                    resultText.className = "success";
                    resultText.innerText = JSON.stringify(data, null, 2);
                } else {
                    resultText.className = "error";
                    resultText.innerText = JSON.stringify(data, null, 2);
                }
            } catch (error) {
                resultBox.style.display = 'block';
                resultText.className = "error";
                resultText.innerText = "Connection Error: " + error.message;
            }
        }
    </script>
</body>
</html>
"""

def load_tokens(region):
    try:
        region_upper = region.upper()
        if region_upper == "IND":
            path = "token_ind.json"
        elif region_upper in {"BR", "US", "SAC", "NA"}:
            path = "token_br.json"
        else:
            path = "token_bd.json"
            
        with open(path, "r") as f:
            tokens = json.load(f)
            return tokens
    except Exception as e:
        app.logger.error(f"Error loading tokens for region {region}: {e}")
        return None

def encrypt_message(plaintext):
    try:
        key = b'Yg&tc%DEuh6%Zc^8'
        iv = b'6oyZDr22E3ychjM%'
        cipher = AES.new(key, AES.MODE_CBC, iv)
        padded_message = pad(plaintext, AES.block_size)
        encrypted_message = cipher.encrypt(padded_message)
        return binascii.hexlify(encrypted_message).decode('utf-8')
    except Exception as e:
        app.logger.error(f"Error encrypting message: {e}")
        return None

def create_protobuf_message(user_id, region):
    try:
        message = like_pb2.like()
        message.uid = int(user_id)
        message.region = region.upper()
        return message.SerializeToString()
    except Exception as e:
        app.logger.error(f"Error creating protobuf message: {e}")
        return None

async def send_request(encrypted_uid, token, url):
    try:
        edata = bytes.fromhex(encrypted_uid)
        headers = {
            "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 9; ASUS_Z01QD Build/PI)",
            "Connection": "Keep-Alive",
            "Accept-Encoding": "gzip",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/x-www-form-urlencoded",
            "Expect": "100-continue",
            "X-Unity-Version": "2018.4.11f1",
            "X-GA": "v1 1",
            "ReleaseVersion": "OB54"
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=edata, headers=headers, timeout=aiohttp.ClientTimeout(total=8)) as response:
                return await response.text()
    except Exception as e:
        return None

async def send_multiple_requests(uid, region, url):
    try:
        protobuf_message = create_protobuf_message(uid, region)
        if protobuf_message is None:
            return None
        encrypted_uid = encrypt_message(protobuf_message)
        if encrypted_uid is None:
            return None
        tokens = load_tokens(region)
        if not tokens:
            return None
            
        tasks = []
        total_requests = min(len(tokens), 50)
        for i in range(total_requests):
            token_item = tokens[i % len(tokens)]
            if isinstance(token_item, dict) and "token" in token_item and token_item["token"] != "N/A":
                tasks.append(send_request(encrypted_uid, token_item["token"], url))
                
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            return results
        return None
    except Exception as e:
        app.logger.error(f"Exception in send_multiple_requests: {e}")
        return None

def create_protobuf(uid):
    try:
        message = uid_generator_pb2.uid_generator()
        message.saturn_ = int(uid)
        message.garena = 1
        return message.SerializeToString()
    except Exception as e:
        app.logger.error(f"Error creating uid protobuf: {e}")
        return None

def enc(uid):
    protobuf_data = create_protobuf(uid)
    if protobuf_data is None:
        return None
    return encrypt_message(protobuf_data)

def make_request(encrypt, region, token):
    try:
        region_upper = region.upper()
        if region_upper == "IND":
            url = "https://client.ind.freefiremobile.com/GetPlayerPersonalShow"
        elif region_upper in {"BR", "US", "SAC", "NA"}:
            url = "https://client.us.freefiremobile.com/GetPlayerPersonalShow"
        else:
            url = "https://clientbp.ggpolarbear.com/GetPlayerPersonalShow"
            
        edata = bytes.fromhex(encrypt)
        headers = {
            "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 9; ASUS_Z01QD Build/PI)",
            "Connection": "Keep-Alive",
            "Accept-Encoding": "gzip",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/x-www-form-urlencoded",
            "Expect": "100-continue",
            "X-Unity-Version": "2018.4.11f1",
            "X-GA": "v1 1",
            "ReleaseVersion": "OB54"
        }
        response = requests.post(url, data=edata, headers=headers, verify=False, timeout=8)
        binary = response.content
        decoded = visit_count_pb2.Info()
        decoded.ParseFromString(binary)
        return decoded
    except Exception as e:
        app.logger.error(f"Error in make_request: {e}")
        return None

@app.route('/', methods=['GET'])
def index():
    # সরাসরি ব্রাউজারে লিংক ওপেন করলে চমৎকার এইচটিএমএল ড্যাশবোর্ড দেখাবে
    return render_template_string(HTML_DASHBOARD)

@app.route('/like', methods=['GET'])
def handle_requests():
    global used_count

    api_key = request.args.get("key")
    if api_key not in VALID_API_KEYS:
        result = OrderedDict([
            ("error", "Invalid or missing API key"),
            ("status", 3)
        ])
        return app.response_class(
            response=json.dumps(result, separators=(',', ':')),
            status=401,
            mimetype='application/json'
        )

    uid = request.args.get("uid")
    region = request.args.get("region", request.args.get("server_name", "")).upper()
    
    if not uid or not region:
        return jsonify({"error": "UID and region (or server_name) are required"}), 400

    try:
        tokens = load_tokens(region)
        if not tokens:
            raise Exception(f"Failed to load tokens for region {region}.")
            
        # সচল টোকেন খুঁজে বের করা (N/A স্কিপ করে)
        valid_token = None
        for t in tokens:
            if isinstance(t, dict) and t.get("token") and t.get("token") != "N/A":
                valid_token = t["token"]
                break
                
        if not valid_token:
            raise Exception(f"No valid/active tokens found in {region} token file.")

        encrypted_uid = enc(uid)
        if encrypted_uid is None:
            raise Exception("Encryption of UID failed.")
            
        before = make_request(encrypted_uid, region, valid_token)
        if before is None or not hasattr(before, 'AccountInfo'):
            raise Exception("Failed to get initial profile info (Token might be expired).")
            
        before_like = before.AccountInfo.Likes

        region_upper = region.upper()
        if region_upper == "IND":
            url = "https://client.ind.freefiremobile.com/LikeProfile"
        elif region_upper in {"BR", "US", "SAC", "NA"}:
            url = "https://client.us.freefiremobile.com/LikeProfile"
        else:
            url = "https://clientbp.ggpolarbear.com/LikeProfile"

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(send_multiple_requests(uid, region, url))
        finally:
            loop.close()

        after = make_request(encrypted_uid, region, valid_token)
        if after is None or not hasattr(after, 'AccountInfo'):
            raise Exception("Failed to get final profile info.")
            
        after_like = after.AccountInfo.Likes
        like_given = after_like - before_like
        status = 1 if like_given > 0 else 2

        if status == 1:
            used_count += 1

        remaining = max(daily_limit - used_count, 0)

        result = OrderedDict([
            ("LikesGivenByAPI", like_given),
            ("LikesafterCommand", after_like),
            ("LikesbeforeCommand", before_like),
            ("PlayerNickname", getattr(after.AccountInfo, 'PlayerNickname', 'Unknown')),
            ("Level", getattr(after.AccountInfo, 'Levels', 0)),
            ("Region", getattr(after.AccountInfo, 'PlayerRegion', region)),
            ("UID", getattr(after.AccountInfo, 'UID', int(uid))),
            ("status", status),
            ("daily_limit", daily_limit),
            ("used", used_count),
            ("remaining", remaining)
        ])

        return app.response_class(
            response=json.dumps(result, separators=(',', ':')),
            status=200,
            mimetype='application/json'
        )

    except Exception as e:
        app.logger.error(f"Backend Processing Error: {e}")
        error_resp = OrderedDict([
            ("error", str(e)),
            ("status", 0)
        ])
        return app.response_class(
            response=json.dumps(error_resp, separators=(',', ':')),
            status=500,
            mimetype='application/json'
        )

@app.route('/remain', methods=['GET'])
def remain_info():
    global used_count
    remaining = max(daily_limit - used_count, 0)
    data = {
        "daily_limit": daily_limit,
        "remaining": remaining,
        "used": used_count,
        "reset_info": "4:00 AM IST"
    }
    return jsonify(data)

if __name__ == '__main__':
    app.run(debug=True)
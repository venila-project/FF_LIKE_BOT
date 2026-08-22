from flask import Flask, request, jsonify
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

# ✅ Valid API keys for Telegram Bot authentication
VALID_API_KEYS = {
    "ZEXXY"  # Telegram bot will use this key
}

# 🔢 Daily limit tracking variables
daily_limit = 200
used_count = 0

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
        # Send up to 50 concurrent requests using available tokens in a loop
        total_requests = min(len(tokens), 50)
        for i in range(total_requests):
            token = tokens[i % len(tokens)]["token"]
            tasks.append(send_request(encrypted_uid, token, url))
            
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return results
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

@app.route('/like', methods=['GET'])
def handle_requests():
    global used_count

    # ✅ API Key Authentication Check
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
            
        token = tokens[0]['token']
        encrypted_uid = enc(uid)
        if encrypted_uid is None:
            raise Exception("Encryption of UID failed.")
            
        # Get like count BEFORE sending likes
        before = make_request(encrypted_uid, region, token)
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

        # Execute asynchronous like requests
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(send_multiple_requests(uid, region, url))
        finally:
            loop.close()

        # Get like count AFTER sending likes
        after = make_request(encrypted_uid, region, token)
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
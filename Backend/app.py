from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import os
import shutil
from SAEMS import *

app = Flask(__name__)
CORS(app)

# ==========================
# FOLDERS SETUP
# ==========================
UPLOAD_FOLDER = "uploads"
OUTPUT_FOLDER = "outputs"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# ==========================
# DB CONNECTION
# ==========================
db = connect_db()

# ==========================
# UPLOAD API
# ==========================
@app.route("/api/upload", methods=["POST"])
def upload():
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]

    if file.filename == "":
        return jsonify({"error": "Empty filename"}), 400

    file_path = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(file_path)

    return jsonify({"path": file_path})


# ==========================
# ENCRYPT API
# ==========================
@app.route("/api/encrypt", methods=["POST"])
def encrypt():
    try:
        data = request.json

        username = data["username"]
        password = data["password"]
        aes_file = data["aes_file"]
        input_video = data["input_video"]
        output_video = data["output_video"]

        # ==========================
        # OUTPUT FIX
        # ==========================
        if not output_video.endswith(".avi"):
            output_video += ".avi"

        output_video = os.path.basename(output_video)
        output_path = os.path.join(OUTPUT_FOLDER, output_video)

        cursor = db.cursor()

        password_hash = hash_password(password)

        # ==========================
        # USER CHECK
        # ==========================
        cursor.execute("SELECT user_id, password_hash FROM USERS WHERE username=%s", (username,))
        result = cursor.fetchone()

        if result:
            user_id, stored_password_hash = result
            if stored_password_hash != password_hash:
                return jsonify({"error": "Incorrect password"})
        else:
            cursor.execute(
                "INSERT INTO USERS (username, password_hash) VALUES (%s,%s)",
                (username, password_hash)
            )
            db.commit()
            user_id = cursor.lastrowid

        # ==========================
        # HASH GENERATION
        # ==========================
        hash_value = generate_sha256(aes_file)

        # ==========================
        # DB INSERTS
        # ==========================
        cursor.execute("INSERT INTO FILES (file_name, user_id) VALUES (%s,%s)",(aes_file, user_id))
        db.commit()
        file_id = cursor.lastrowid


            # INSERT INTO AES_FILES
        cursor.execute("INSERT INTO AES_FILES (file_id, aes_file_path) VALUES (%s,%s)",(file_id, aes_file))
        db.commit()
        aes_file_id = cursor.lastrowid


            # 🔥 INSERT INTO STORED_HASH (THIS IS MISSING / WRONG)
        cursor.execute("INSERT INTO STORED_HASH (aes_file_id, hash_value) VALUES (%s,%s)",(aes_file_id, hash_value))
        db.commit()
        aes_hash_id = cursor.lastrowid

        cursor.execute(
            "INSERT INTO VIDEOS (video_name, video_path, aes_hash_id) VALUES (%s,%s,%s)",(output_video, output_path, aes_hash_id)
        )
        db.commit()

        # ==========================
        # VIDEO PROCESSING
        # ==========================
        embed_hash_into_video(input_video, output_path, hash_value)
        print("Embedding hash:", hash_value)
        print("✅ Hash embedded successfully.")

        # ==========================
        # RETURN FILE (DOWNLOAD)
        # ==========================
        return send_file(
            output_path,
            as_attachment=True,
            download_name=output_video,
            mimetype="video/avi"
        )

    except Exception as e:
        return jsonify({"error": str(e)})


# ==========================
# VERIFY API (FIXED)
# ==========================
@app.route("/api/verify", methods=["POST"])
def verify():
    try:
        data = request.json
        print("🚀 Verify API HIT")
        video_filename = data["video"]
        video_filename = os.path.join("outputs", os.path.basename(video_filename))
        aes_filename = data["aes"]

        cursor = db.cursor(buffered=True)

        aes_name = aes_filename.replace("/", "\\").strip() 
        recalculated_hash = generate_sha256(aes_filename)

        cursor.execute("""
            SELECT sh.hash_value, sh.aes_hash_id, af.aes_file_id, af.file_id
            FROM STORED_HASH sh
            JOIN AES_FILES af ON sh.aes_file_id = af.aes_file_id
            JOIN FILES f ON af.file_id = f.file_id
            WHERE f.file_name = %s
        """, (aes_name,))
        
        result = cursor.fetchone()
        
        if result is None:
            return jsonify({"status": "No record found"}), 404

        stored_hash, aes_hash_id, aes_file_id, file_id = result
        video_hash = extract_hash_from_video(video_filename)

        # ✅ AUTHENTIC CASE
        if stored_hash == video_hash:
            return jsonify({"status": "AUTHENTIC"})

        # 🔥 TAMPERED CASE (Indentation Fixed)
        else:
            print("❌ Tampering detected! Preparing backup...") 
            backup_filename = "backup_" + os.path.basename(aes_filename)
            backup_path = os.path.join("outputs", backup_filename)

            # Create the backup copy inside the logic block
            shutil.copy(aes_filename, backup_path)

            response = send_file(
                backup_path,
                as_attachment=True,
                download_name=backup_filename,
                mimetype="application/octet-stream"
            )
            # Add a custom header to help the React frontend identify the file
            response.headers["X-File-Status"] = "Tampered-Backup"
            return response

    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"error": str(e)}), 500
# ==========================
# RUN SERVER
# ==========================
if __name__ == "__main__":
    app.run(port=5000, debug=True)


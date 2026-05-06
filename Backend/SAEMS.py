import cv2
import hashlib
import mysql.connector
import shutil
import os


# ==========================================
# DATABASE CONNECTION (NO INPUT REQUIRED)
# ==========================================

def connect_db():

    db = mysql.connector.connect(
        host="localhost",
        user="root",          # change if needed
        password="root",      # 🔹 PUT YOUR PASSWORD HERE
        database="saems"
    )

    return db


# ==========================================
# HASH PASSWORD
# ==========================================

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()


# ==========================================
# GENERATE SHA256 HASH OF FILE
# ==========================================

def generate_sha256(file_path):
    sha = hashlib.sha256()

    with open(file_path, "rb") as f:
        while True:
            data = f.read(4096)
            if not data:
                break
            sha.update(data)

    return sha.hexdigest()


# ==========================================
# EMBED HASH INTO VIDEO
# ==========================================

def embed_hash_into_video(input_video, output_video, hash_value):
    cap = cv2.VideoCapture(input_video)

    width = int(cap.get(3))
    height = int(cap.get(4))
    fps = int(cap.get(5))

    # ✅ CHANGE IS HERE
    out = cv2.VideoWriter(
        output_video,
        cv2.VideoWriter_fourcc(*'FFV1'),
        fps,
        (width, height)
    )

    ret, frame = cap.read()

    for i in range(64):
        frame[0, i][0] = ord(hash_value[i])

    out.write(frame)

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        out.write(frame)

    cap.release()
    out.release()

# ==========================================
# EXTRACT HASH FROM VIDEO
# ==========================================

def extract_hash_from_video(video_path):
    cap = cv2.VideoCapture(video_path)

    if not cap.isOpened():

        return ""

    ret, frame = cap.read()

    if not ret:
        return ""

    hash_chars = []

    try:
        for i in range(64):
            val = int(frame[0, i][0])
            hash_chars.append(chr(val))

        extracted = ''.join(hash_chars)

        print("Extracted hash:", extracted)

        cap.release()
        return extracted

    except Exception as e:
        print("❌ Extraction error:", e)
        cap.release()
        return ""

# ==========================================
# ENCRYPTION PHASE
# ==========================================

def encryption_phase(db):

    cursor = db.cursor()

    username = input("Enter username: ")
    password = input("Enter password: ")

    password_hash = hash_password(password)

    cursor.execute("SELECT user_id, password_hash FROM USERS WHERE username=%s", (username,))
    result = cursor.fetchone()

    if result:
        user_id, stored_password_hash = result
        if stored_password_hash != password_hash:
            print("Incorrect password!")
            return
    else:
        cursor.execute("INSERT INTO USERS (username, password_hash) VALUES (%s,%s)",
                       (username, password_hash))
        db.commit()
        user_id = cursor.lastrowid

    aes_file = input("Enter AES filename: ")
    input_video = input("Enter input video filename: ")
    output_video = input("Enter output video filename (.avi): ")

    hash_value = generate_sha256(aes_file)

    cursor.execute("INSERT INTO FILES (file_name, user_id) VALUES (%s,%s)",
                   (aes_file, user_id))
    db.commit()
    file_id = cursor.lastrowid

    cursor.execute("INSERT INTO AES_FILES (file_id, aes_file_path) VALUES (%s,%s)",
                   (file_id, aes_file))
    db.commit()
    aes_file_id = cursor.lastrowid

    cursor.execute("INSERT INTO STORED_HASH (aes_file_id, hash_value) VALUES (%s,%s)",
                   (aes_file_id, hash_value))
    db.commit()
    aes_hash_id = cursor.lastrowid

    cursor.execute("INSERT INTO VIDEOS (video_name, video_path, aes_hash_id) VALUES (%s,%s,%s)",
                   (output_video, output_video, aes_hash_id))
    db.commit()

    embed_hash_into_video(input_video, output_video, hash_value)


# ==========================================
# VERIFICATION PHASE
# ==========================================

def verification_phase(db):

    cursor = db.cursor(buffered=True)

    video_filename = input("Enter video filename (.avi): ")
    aes_filename = input("Enter AES filename: ")

    recalculated_hash = generate_sha256(aes_filename)

    cursor.execute("""
        SELECT sh.hash_value, sh.aes_hash_id, af.aes_file_id, af.file_id
        FROM STORED_HASH sh
        JOIN AES_FILES af ON sh.aes_file_id = af.aes_file_id
        JOIN FILES f ON af.file_id = f.file_id
        WHERE f.file_name = %s
    """, (aes_filename,))

    result = cursor.fetchone()

    if result is None:
        print("No record found.")
        return

    stored_hash, aes_hash_id, aes_file_id, file_id = result
    video_hash = extract_hash_from_video(video_filename)

    # ==========================================
    # FILE RETURN LOGIC (FINAL FIXED)
    # ==========================================

    if stored_hash == video_hash == recalculated_hash:

        print("FILE IS AUTHENTIC")

        # Create request file ONLY if authentic
        request_filename = "request_" + os.path.basename(aes_filename)
        shutil.copy(aes_filename, request_filename)

        cursor.execute("""
            INSERT INTO DECRYPTED_FILE (aes_file_id)
            VALUES (%s)
        """, (aes_file_id,))
        db.commit()

    else:

        print("FILE IS TAMPERED")

        # Create ONLY backup file
        backup_filename = "backup_" + os.path.basename(aes_filename)
        shutil.copy(aes_filename, backup_filename)

        cursor.execute("""
            INSERT INTO BACK_UP (file_id, backup_path)
            VALUES (%s, %s)
        """, (file_id, backup_filename))
        db.commit()

    print("Verification completed.")


# ==========================================
# MAIN
# ==========================================

if __name__ == "__main__":

    db = connect_db()

    print("1. Encryption Phase")
    print("2. Verification Phase")

    choice = input("Enter choice (1/2): ")

    if choice == "1":
        encryption_phase(db)
    elif choice == "2":
        verification_phase(db)
    else:
        print("Invalid choice.")
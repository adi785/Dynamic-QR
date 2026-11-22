import csv
import io
import os
import re
import zipfile
import qrcode
from PIL import Image

# Import Flask app and models
from app import app, db
from models import TShirt, generate_unique_tshirt_id

CSV_DATA = """Name,Year,Size,3 Digit Lucky Number,Character Name,,,,,,,,,
Aakriti Agarwal,1,M,170,Nobara Kugisaki,,,,,,,,,
Aarti shaw,2,S,015,LADY PARADOX,,,,,,,,,
Aarushi Srivastava,2,M,167,KIKI,,,,,,,,,
Aayushi Bagora,2,XL,127,Tony Stark,,,,,,,,,
Abhinav jaiswal,1,M,711,Atsu Muerté,,,,,,,,,
Adarsh Soni,1,M,007,SUNG JINWOO,,,,,,,,,
Adiba Mohsin,1,L,012,Lightening McQueen,,,,,,,,,
Aditya Falor,2,XL,022,Mythical Ace,,,,,,,,,
Aditya Sharma,2,L,199,Might Guy,,,,,,,,,
Aishwarya bhatnagar,1,M,100,GODDESS MODE,,,,,,,,,
Akshara gautam,1,XL,014,heer,,,,,,,,,
Akshat Dokania,1,XXL,007,ETHAN HUNT,,,,,,,,,
Akshita Shrivastava,1,M,101,NYXARA,,,,,,,,,
Akshra Agarwal,2,XL,7134,MIRACULOUS,,,,,,,,,
Alice Sharma,2,S,201,Invincible,,,,,,,Size,Count,Share of Total
Amitesh Tyagi,1,XXL,369,Omega,,,,,,,M,56,33.90%
Anmol Divyanshu,1,L,018,Sung Jinwoo,,,,,,,L,37,22.40%
Anmol Sharma,1,M,010,Anmol,,,,,,,S,31,18.80%
Anuradha Verma,2,S,111,ELIXCEO,,,,,,,XL,21,12.70%
Anusha kocheta,2,M,327,NOBARA KUGISAKI,,,,,,,XXL,18,10.90%
Apurva Rastogi,2,S,001,IRONHEART,,,,,,,MISSING,2,1.20%
Archit pareek,2,M,914,ARVASTRA,,,,,,,TOTAL,165,100%
Ariha jain,1,S,181,Elizabeth swann,,,,,,,,,
Arpan Shrivastava,3,L,029,Spirit,,,,,,,,,
Ashutosh,4,M,025,AK,,,,,,,,,
Ausaf Ahmed,,,,,,,,,,,,,
Avni Bindal,1,S,415,ALTERYX,,,,,,,,,
AYUSH GOYAL,1,XL,009,AYUSH,,,,,,,,,
Ayush Sharma,2,M,013,Quantum Mind,,,,,,,,,
Bhavik guleriya,1,XXL,420,BITTU,,,,,,,,,
Bhavya Gaur,1,XL,030,Vocal engineer,,,,,,,,,
Bhavya Jindal,2,S,736,Hiro Hamada,,,,,,,,,
Bhavya Khatri,1,XL,109,BATMAN,,,,,,,,,
Chandan Ghusinga,1,M,093,Yoriichi Tsugikuni,,,,,,,,,
Danish,2,L,009,DANISH BHAI,,,,,,,,,
Darshila Sain,1,M,073,Raven,,,,,,,,,
Deepak Maharia,1,XL,002,Jimmy,,,,,,,,,
Devansh Jain,1,L,008,Roger,,,,,,,,,
Devesh Sharma,1,XL,888,IMMORTAL KNIGHT,,,,,,,,,
Dhara Sharma,2,M,264,Captain Marvel,,,,,,,,,
Diksha Mathur,2,S,028,PHOENIX,,,,,,,,,
Disha Jain,2,L,018,DISHA DJ 18,,,,,,,,,
Divya Rajwani,1,M,116,Hermione Granger,,,,,,,,,
Divyansh Sharma,1,L,777,STARK,,,,,,,,,
Durga Singh,2,M,848,Baba Yaga,,,,,,,,,
Fuzail Johar,1,XL,07,IRON MAN,,,,,,,,,
GANESH Sharma,1,L,3,HACKER Ganesh,,,,,,,,,
Garima arora,1,S,145,NEO,,,,,,,,,
Gaurav kumar,1,L,125,Kaneki,,,,,,,,,
Gauri Tandon,2,L,721,The Cipher,,,,,,,,,
Goon Jain,2,M,017,Penguin,,,,,,,,,
Gopal Krishn Jha,1,XXL,069,MONKEY D. LUFFY,,,,,,,,,
Hardik Singhal,2,XXL,007,STARK,,,,,,,,,
Harsh Sharma,1,XXL,8686,HARSH X BIKER X CINEMATOGRAPHER,,,,,,,,,
Harshil Diwan,2,M,369,Mark XLVI,,,,,,,,,
Harshit Bijalwan,1,L,031,JRVIS,,,,,,,,,
Harshit Bothra,1,L,007,Shinchan Nohara,,,,,,,,,
HARSHIT SAINI,1,M,031,Jarvis,,,,,,,,,
Harshita Yadav,2,L,111,WARSONG,,,,,,,,,
Himadri Mishra,2,M,505,RAVEN,,,,,,,,,
Himanshi Bhagnani,1,M,156,SHURY,,,,,,,,,
Himanshu Baberwal,2,L,127,,,,,,,,,,
Himanshu Tank,1,M,007,Verstappen,,,,,,,,,
Hitanshi Jain,2,S,017,STARKNOVA,,,,,,,,,
Ihita Sinha,3,S,949,Rachel,,,,,,,,,
Ipshita Tripathi,1,S,205,Elysian Désirée,,,,,,,,,
Ishan Verma,1,XXL,837,IVX,,,,,,,,,
Kanak mangal,1,M,777,Deathsync,,,,,,,,,
Kanishk Pachlangia,2,M,007,BATMAN,,,,,,,,,
Karan Jadaun,2,L,001,IGRIS,,,,,,,,,
Kartik Mahawar,1,L,3000,IRON MAN,,,,,,,,,
Kashyap Tiwari,1,M,030,Levi Ackerman,,,,,,,,,
Kavya Sagwaria,1,XL,016,KAVYA,,,,,,,,,
Khushi Gupta,2,M,015,V.E.R.O.N.I.C.A,,,,,,,,,
Khushi Kaushik,1,M,024,Blair Waldorf,,,,,,,,,
Khyati Khandelwal,1,XXL,009,Witch,,,,,,,,,
Krishi Mahnot,1,M,124,Snoopy,,,,,,,,,
Krishna Tayal,2,XXL,001,DAREDEVIL,,,,,,,,,
Kulpreet Kaur,1,M,006,Murphy Cooper,,,,,,,,,
Lakshya,3,L,143,JACK SPARROW,,,,,,,,,
Lavish,1,M,018,LAVISHXD,,,,,,,,,
Lucky,1,S,018,Jean Grey,,,,,,,,,
Madhav Karnani,1,M,238,HACKER,,,,,,,,,
Milind Varlani,2,XXL,067,Iron Man,,,,,,,,,
Mohit Malviya,2,S,347,GOJO SATORU,,,,,,,,,
Mohit Saini,1,M,202,Muted Tempest,,,,,,,,,
Mrinal Pandey,1,XL,169,Yorichi,,,,,,,,,
Muskan,2,M,77,BUCKLEY,,,,,,,,,
Muskan sukariya,2,S,020,Muskan sukariya,,,,,,,,,
Naksh Prajapati,1,S,225,Specter,,,,,,,,,
Naman Sharma,2,L,001,Merchant Of Death,,,,,,,,,
Nandani Gupta,1,L,107,Nightfury,,,,,,,,,
NIKHIL SHARMA,1,M,831,Shadow Prime,,,,,,,,,
Ojasv jain,2,M,024,Doctor Strange,,,,,,,,,
Palak Sharma,1,M,017,Hermione Granger,,,,,,,,,
Paridhi poddar,2,S,747,Pikachu,,,,,,,,,
Prachi Chauhan,2,M,022,Tony STARK,,,,,,,,,
Pragyan agarwal,1,XL,008,Benn Tennyson,,,,,,,,,
Prakhar Bhardwaj,1,XXL,13,Prakhar,,,,,,,,,
Pramod singh,1,XL,777,TECH TITAN,,,,,,,,,
Pranjal Manish matolia,1,XXL,067,Luffy,,,,,,,,,
Prashant,2,L,999,avtar,,,,,,,,,
Prashuk jain,1,XXL,208,RA-one,,,,,,,,,
Prateek haritwal,1,L,108,Bajrangi,,,,,,,,,
Preet shah,1,XL,007,Optimas prime,,,,,,,,,
Prerana,2,L,666,Prerana,,,,,,,,,
Priyan Banger,2,M,777,Banger,,,,,,,,,
Priyanshu,1,L,056,MONKEY D LUFFY,,,,,,,,,
Priyanshu Yadav,1,XL,147,PRIYANSHU YADAV,,,,,,,,,
Purva Khare,2,S,224,Piku,,,,,,,,,
Rahul Kaswan,1,L,018,VIRAT KOHLI,,,,,,,,,
Raj Singh,1,M,27,Levi Ackerman,,,,,,,,,
Rashi Advani,2,M,013,CYPHER,,,,,,,,,
Ravish,1,L,108,Ravish,,,,,,,,,
Rhythm Goyal,1,M,000,Mr. Robot,,,,,,,,,
Richal Agarwal,1,L,257,Aurora Serpentis,,,,,,,,,
Riya Gupta,1,M,008,ELEVEN ( EL),,,,,,,,,
Riya jindal,2,S,009,Riya,,,,,,,,,
riya lalwani,1,S,725,RIO,,,,,,,,,
Robin Singh,2,L,007,Zenix,,,,,,,,,
Rounak kapoor,2,L,016,Harry Potter,,,,,,,,,
Rudra Pratap Singh Kilanot,1,M,006,Ghost Reaper,,,,,,,,,
Rudraksh Agarwal,1,XXL,016,RUDRAKSH,,,,,,,,,
Rudraksh Rohira,1,L,69,RYU,,,,,,,,,
Rupesh Choudhary,1,M,404,ZeroTrace,,,,,,,,,
Saar Singhal,,,,,,,,,,,,,
Saksham Khandelwal,1,S,246,OBSIDIAN,,,,,,,,,
Samarth Jain,1,XXL,887,UZUMAKI NARUTO,,,,,,,,,
Samir Sharma,1,L,128,ArduinoRobo,,,,,,,,,
Samkit Jain,2,XXL,067,Omen,,,,,,,,,
Samriddhi Sunshine Gupta,1,M,217,Sunshine,,,,,,,,,
Samyak jain,2,M,012,DARK KNIGHT,,,,,,,,,
Samyak Kasliwal,2,L,777,REHMAN DAKAIT,,,,,,,,,
Sarvesh sehra,1,XL,101,OROCHIMARU,,,,,,,,,
Shailesh Meena,1,XL,026,The Horizon,,,,,,,,,
Shamita Srivastava,3,S,888,Allie,,,,,,,,,
Shivangi sharma,1,M,306,Mayshi Yukishiro,,,,,,,,,
Shivansh Sharma,1,L,849,Howard Stark,,,,,,,,,
Shourya Bhargava,2,L,047,Leon Kennedy,,,,,,,,,
Shreeji Pandey,1,S,289,Hermione Granger,,,,,,,,,
Shruti Bhardwaj,1,XL,108,HINATA_UZUMAKI,,,,,,,,,
Shruti Delu,2,S,021,SUKI,,,,,,,,,
Siddharth Gupta,2,M,966,Mr. Bean,,,,,,,,,
Snehal Jain,1,S,888,EMPRESS,,,,,,,,,
SOMAN SINGHAL,2,XXL,023,GHOSTBYTE,,,,,,,,,
Sreyasee Basu,1,S,007,Sushi,,,,,,,,,
Srija Srivastav,2,S,037,The Tesseract,,,,,,,,,
Suhani Dhingra,1,M,005,IRIS,,,,,,,,,
Suvigya,2,S,023,Scarlet witch,,,,,,,,,
Tanmay Jain,1,XXL,719,JARVISX719,,,,,,,,,
Tarun Vashishth,1,M,001,Vanta,,,,,,,,,
Teerath Jangid,1,M,008,Monkey D Luffy,,,,,,,,,
Tosif Mansuri,1,M,019,V-EON,,,,,,,,,
Trishala narayan nagar,1,S,006,JIGGLYPUFF,,,,,,,,,
Umang Raj,1,XL,003,LEON S. KENNEDY,,,,,,,,,
Vaishnavi Sharma,1,M,089,EIJI,,,,,,,,,
Vanshika shihani,1,M,204,MULAN,,,,,,,,,
Vibhor sharma,1,M,001,TONY STARK,,,,,,,,,
Vidhi Agrawal,2,S,456,Pocoyo,,,,,,,,,
Vishal mahala,2,L,018,SPIDERMAN,,,,,,,,,
Yajan singh vashishth,1,XL,009,SPIDERMAN,,,,,,,,,
Yash Ajwani,1,L,111,Kim dokja,,,,,,,,,
Yashwi Rathi,1,M,404,Pheonix,,,,,,,,,
Yogita Thacker,1,S,030,The glitch,,,,,,,,,
Bhairav Sarswat,2,L,308,Mr. Antique Parker,,,,,,,,,
"""

def clean_slug(raw_str):
    s = re.sub(r'[^a-zA-Z0-9_-]', '_', raw_str.strip())
    s = re.sub(r'_+', '_', s).strip('_')
    return s[:32]

def run_import():
    reader = csv.reader(io.StringIO(CSV_DATA.strip()))
    rows = list(reader)[1:] # Skip header

    # Ensure output directory for QR codes exists
    qr_dir = os.path.join(app.root_path, "static", "qrcodes")
    os.makedirs(qr_dir, exist_ok=True)
    zip_path = os.path.join(app.root_path, "static", "all_member_qr_codes.zip")

    with app.app_context():
        # First, remove test placeholder Tarun Meena if present
        tarun = TShirt.query.filter_by(id="TSH0000001").first()
        if tarun:
            db.session.delete(tarun)
            db.session.commit()
            print("Removed placeholder test record TSH0000001.")

        used_slugs = {}
        for existing in TShirt.query.all():
            used_slugs[existing.slug.lower()] = existing.id

        created_count = 0
        updated_count = 0
        all_records = []

        for row in rows:
            name = row[0].strip()
            year = row[1].strip() if len(row) > 1 else ""
            size = row[2].strip() if len(row) > 2 else ""
            lucky = row[3].strip() if len(row) > 3 else ""
            char = row[4].strip() if len(row) > 4 else ""

            # Slug determination
            base_slug = char if char else name
            slug = clean_slug(base_slug)
            if not slug:
                slug = clean_slug(name)

            # Handle collision
            if slug.lower() in used_slugs and used_slugs[slug.lower()] != name:
                # Try with lucky number or first name
                alt = clean_slug(f"{base_slug}_{lucky}") if lucky else clean_slug(f"{base_slug}_{name.split()[0]}")
                if alt.lower() in used_slugs and used_slugs[alt.lower()] != name:
                    alt = clean_slug(f"{base_slug}_{name.split()[0]}")
                slug = alt

            # Check if this member is already in DB (by name or slug)
            existing = TShirt.query.filter((TShirt.member_name == name) | (TShirt.slug == slug)).first()

            if existing:
                # Update existing record
                existing.member_name = name
                existing.slug = slug
                existing.member_role = "MEMBER"
                existing.member_message = "Official Association Member. Scan anytime to connect!"
                existing.member_phone = None
                existing.accent_color = "#dc2626"
                existing.member_email = "abc@gmail.com"
                db.session.add(existing)
                used_slugs[slug.lower()] = existing.id
                all_records.append((existing, slug, name, char))
                updated_count += 1
            else:
                # Create new record
                tshirt_id = generate_unique_tshirt_id()
                new_shirt = TShirt(
                    id=tshirt_id,
                    slug=slug,
                    member_name=name,
                    member_role="MEMBER",
                    member_message="Official Association Member. Scan anytime to connect!",
                    member_phone=None,
                    member_email="abc@gmail.com",
                    accent_color="#dc2626",
                    scan_count=0
                )
                db.session.add(new_shirt)
                used_slugs[slug.lower()] = tshirt_id
                all_records.append((new_shirt, slug, name, char))
                created_count += 1

        db.session.commit()
        print(f"Database sync complete! Created: {created_count}, Updated: {updated_count}, Total: {len(all_records)}")

        # Now generate high-res QR codes for all records
        base_url = app.config.get("BASE_URL", "http://127.0.0.1:5000")
        qr_files = []

        for shirt, slug, name, char in all_records:
            target_url = f"{base_url}/t/{slug}"
            qr = qrcode.QRCode(
                version=None,
                error_correction=qrcode.constants.ERROR_CORRECT_H,
                box_size=10,
                border=2,
            )
            qr.add_data(target_url)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white").convert("RGB")

            # Clean filename
            safe_filename = f"{slug}_qr.png"
            file_path = os.path.join(qr_dir, safe_filename)
            img.save(file_path, format="PNG")
            qr_files.append((file_path, safe_filename))

        # Bundle into ZIP archive
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            for file_path, arcname in qr_files:
                zipf.write(file_path, arcname)

        print(f"Generated {len(qr_files)} QR code PNG files in '{qr_dir}'.")
        print(f"Created complete ZIP bundle at '{zip_path}'.")

if __name__ == "__main__":
    run_import()

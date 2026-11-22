"""
roster_data.py
Contains official member roster and automated database sync logic for local and deployed environments.
"""
import re

ROSTER_RECORDS = [
    ("Aakriti Agarwal", "Nobara Kugisaki", "170"),
    ("Aarti shaw", "LADY PARADOX", "015"),
    ("Aarushi Srivastava", "KIKI", "167"),
    ("Aayushi Bagora", "Tony Stark", "127"),
    ("Abhinav jaiswal", "Atsu Muerté", "711"),
    ("Adarsh Soni", "SUNG JINWOO", "007"),
    ("Adiba Mohsin", "Lightening McQueen", "012"),
    ("Aditya Falor", "Mythical Ace", "022"),
    ("Aditya Sharma", "Might Guy", "199"),
    ("Aishwarya bhatnagar", "GODDESS MODE", "100"),
    ("Akshara gautam", "heer", "014"),
    ("Akshat Dokania", "ETHAN HUNT", "007"),
    ("Akshita Shrivastava", "NYXARA", "101"),
    ("Akshra Agarwal", "MIRACULOUS", "7134"),
    ("Alice Sharma", "Invincible", "201"),
    ("Amitesh Tyagi", "Omega", "369"),
    ("Anmol Divyanshu", "Sung Jinwoo", "018"),
    ("Anmol Sharma", "Anmol", "010"),
    ("Anuradha Verma", "ELIXCEO", "111"),
    ("Anusha kocheta", "NOBARA KUGISAKI", "327"),
    ("Apurva Rastogi", "IRONHEART", "001"),
    ("Archit pareek", "ARVASTRA", "914"),
    ("Ariha jain", "Elizabeth swann", "181"),
    ("Arpan Shrivastava", "Spirit", "029"),
    ("Ashutosh", "AK", "025"),
    ("Ausaf Ahmed", "", ""),
    ("Avni Bindal", "ALTERYX", "415"),
    ("AYUSH GOYAL", "AYUSH", "009"),
    ("Ayush Sharma", "Quantum Mind", "013"),
    ("Bhavik guleriya", "BITTU", "420"),
    ("Bhavya Gaur", "Vocal engineer", "030"),
    ("Bhavya Jindal", "Hiro Hamada", "736"),
    ("Bhavya Khatri", "BATMAN", "109"),
    ("Chandan Ghusinga", "Yoriichi Tsugikuni", "093"),
    ("Danish", "DANISH BHAI", "009"),
    ("Darshila Sain", "Raven", "073"),
    ("Deepak Maharia", "Jimmy", "002"),
    ("Devansh Jain", "Roger", "008"),
    ("Devesh Sharma", "IMMORTAL KNIGHT", "888"),
    ("Dhara Sharma", "Captain Marvel", "264"),
    ("Diksha Mathur", "PHOENIX", "028"),
    ("Disha Jain", "DISHA DJ 18", "018"),
    ("Divya Rajwani", "Hermione Granger", "116"),
    ("Divyansh Sharma", "STARK", "777"),
    ("Durga Singh", "Baba Yaga", "848"),
    ("Fuzail Johar", "IRON MAN", "07"),
    ("GANESH Sharma", "HACKER Ganesh", "3"),
    ("Garima arora", "NEO", "145"),
    ("Gaurav kumar", "Kaneki", "125"),
    ("Gauri Tandon", "The Cipher", "721"),
    ("Goon Jain", "Penguin", "017"),
    ("Gopal Krishn Jha", "MONKEY D. LUFFY", "069"),
    ("Hardik Singhal", "STARK", "007"),
    ("Harsh Sharma", "HARSH X BIKER X CINEMATOGRAPHER", "8686"),
    ("Harshil Diwan", "Mark XLVI", "369"),
    ("Harshit Bijalwan", "JRVIS", "031"),
    ("Harshit Bothra", "Shinchan Nohara", "007"),
    ("HARSHIT SAINI", "Jarvis", "031"),
    ("Harshita Yadav", "WARSONG", "111"),
    ("Himadri Mishra", "RAVEN", "505"),
    ("Himanshi Bhagnani", "SHURY", "156"),
    ("Himanshu Baberwal", "", "127"),
    ("Himanshu Tank", "Verstappen", "007"),
    ("Hitanshi Jain", "STARKNOVA", "017"),
    ("Ihita Sinha", "Rachel", "949"),
    ("Ipshita Tripathi", "Elysian Désirée", "205"),
    ("Ishan Verma", "IVX", "837"),
    ("Kanak mangal", "Deathsync", "777"),
    ("Kanishk Pachlangia", "BATMAN", "007"),
    ("Karan Jadaun", "IGRIS", "001"),
    ("Kartik Mahawar", "IRON MAN", "3000"),
    ("Kashyap Tiwari", "Levi Ackerman", "030"),
    ("Kavya Sagwaria", "KAVYA", "016"),
    ("Khushi Gupta", "V.E.R.O.N.I.C.A", "015"),
    ("Khushi Kaushik", "Blair Waldorf", "024"),
    ("Khyati Khandelwal", "Witch", "009"),
    ("Krishi Mahnot", "Snoopy", "124"),
    ("Krishna Tayal", "DAREDEVIL", "001"),
    ("Kulpreet Kaur", "Murphy Cooper", "006"),
    ("Lakshya", "JACK SPARROW", "143"),
    ("Lavish", "LAVISHXD", "018"),
    ("Lucky", "Jean Grey", "018"),
    ("Madhav Karnani", "HACKER", "238"),
    ("Milind Varlani", "Iron Man", "067"),
    ("Mohit Malviya", "GOJO SATORU", "347"),
    ("Mohit Saini", "Muted Tempest", "202"),
    ("Mrinal Pandey", "Yorichi", "169"),
    ("Muskan", "BUCKLEY", "77"),
    ("Muskan sukariya", "Muskan sukariya", "020"),
    ("Naksh Prajapati", "Specter", "225"),
    ("Naman Sharma", "Merchant Of Death", "001"),
    ("Nandani Gupta", "Nightfury", "107"),
    ("NIKHIL SHARMA", "Shadow Prime", "831"),
    ("Ojasv jain", "Doctor Strange", "024"),
    ("Palak Sharma", "Hermione Granger", "017"),
    ("Paridhi poddar", "Pikachu", "747"),
    ("Prachi Chauhan", "Tony STARK", "022"),
    ("Pragyan agarwal", "Benn Tennyson", "008"),
    ("Prakhar Bhardwaj", "Prakhar", "13"),
    ("Pramod singh", "TECH TITAN", "777"),
    ("Pranjal Manish matolia", "Luffy", "067"),
    ("Prashant", "avtar", "999"),
    ("Prashuk jain", "RA-one", "208"),
    ("Prateek haritwal", "Bajrangi", "108"),
    ("Preet shah", "Optimas prime", "007"),
    ("Prerana", "Prerana", "666"),
    ("Priyan Banger", "Banger", "777"),
    ("Priyanshu", "MONKEY D LUFFY", "056"),
    ("Priyanshu Yadav", "PRIYANSHU YADAV", "147"),
    ("Purva Khare", "Piku", "224"),
    ("Rahul Kaswan", "VIRAT KOHLI", "018"),
    ("Raj Singh", "Levi Ackerman", "27"),
    ("Rashi Advani", "CYPHER", "013"),
    ("Ravish", "Ravish", "108"),
    ("Rhythm Goyal", "Mr. Robot", "000"),
    ("Richal Agarwal", "Aurora Serpentis", "257"),
    ("Riya Gupta", "ELEVEN ( EL)", "008"),
    ("Riya jindal", "Riya", "009"),
    ("riya lalwani", "RIO", "725"),
    ("Robin Singh", "Zenix", "007"),
    ("Rounak kapoor", "Harry Potter", "016"),
    ("Rudra Pratap Singh Kilanot", "Ghost Reaper", "006"),
    ("Rudraksh Agarwal", "RUDRAKSH", "016"),
    ("Rudraksh Rohira", "RYU", "69"),
    ("Rupesh Choudhary", "ZeroTrace", "404"),
    ("Saar Singhal", "", ""),
    ("Saksham Khandelwal", "OBSIDIAN", "246"),
    ("Samarth Jain", "UZUMAKI NARUTO", "887"),
    ("Samir Sharma", "ArduinoRobo", "128"),
    ("Samkit Jain", "Omen", "067"),
    ("Samriddhi Sunshine Gupta", "Sunshine", "217"),
    ("Samyak jain", "DARK KNIGHT", "012"),
    ("Samyak Kasliwal", "REHMAN DAKAIT", "777"),
    ("Sarvesh sehra", "OROCHIMARU", "101"),
    ("Shailesh Meena", "The Horizon", "026"),
    ("Shamita Srivastava", "Allie", "888"),
    ("Shivangi sharma", "Mayshi Yukishiro", "306"),
    ("Shivansh Sharma", "Howard Stark", "849"),
    ("Shourya Bhargava", "Leon Kennedy", "047"),
    ("Shreeji Pandey", "Hermione Granger", "289"),
    ("Shruti Bhardwaj", "HINATA_UZUMAKI", "108"),
    ("Shruti Delu", "SUKI", "021"),
    ("Siddharth Gupta", "Mr. Bean", "966"),
    ("Snehal Jain", "EMPRESS", "888"),
    ("SOMAN SINGHAL", "GHOSTBYTE", "023"),
    ("Sreyasee Basu", "Sushi", "007"),
    ("Srija Srivastav", "The Tesseract", "037"),
    ("Suhani Dhingra", "IRIS", "005"),
    ("Suvigya", "Scarlet witch", "023"),
    ("Tanmay Jain", "JARVISX719", "719"),
    ("Tarun Vashishth", "Vanta", "001"),
    ("Teerath Jangid", "Monkey D Luffy", "008"),
    ("Tosif Mansuri", "V-EON", "019"),
    ("Trishala narayan nagar", "JIGGLYPUFF", "006"),
    ("Umang Raj", "LEON S. KENNEDY", "003"),
    ("Vaishnavi Sharma", "EIJI", "089"),
    ("Vanshika shihani", "MULAN", "204"),
    ("Vibhor sharma", "TONY STARK", "001"),
    ("Vidhi Agrawal", "Pocoyo", "456"),
    ("Vishal mahala", "SPIDERMAN", "018"),
    ("Yajan singh vashishth", "SPIDERMAN", "009"),
    ("Yash Ajwani", "Kim dokja", "111"),
    ("Yashwi Rathi", "Pheonix", "404"),
    ("Yogita Thacker", "The glitch", "030"),
    ("Bhairav Sarswat", "Mr. Antique Parker", "308"),
]

def clean_slug(raw_str):
    s = re.sub(r'[^a-zA-Z0-9_-]', '_', raw_str.strip())
    s = re.sub(r'_+', '_', s).strip('_')
    return s[:32]

def get_planned_roster():
    """Builds unique, URL-safe slugs for all roster records."""
    used_slugs = set()
    planned = []
    for name, char, lucky in ROSTER_RECORDS:
        base = char if char else name
        cand = clean_slug(base)
        if not cand:
            cand = clean_slug(name)

        if cand.lower() in used_slugs:
            alt = clean_slug(f"{base}_{lucky}") if lucky else clean_slug(f"{base}_{name.split()[0]}")
            if alt.lower() in used_slugs:
                alt = clean_slug(f"{base}_{name.split()[0]}")
            cand = alt

        used_slugs.add(cand.lower())
        planned.append({
            "name": name,
            "char": char,
            "lucky": lucky,
            "slug": cand,
        })
    return planned

def seed_roster_into_db(db, TShirt, generate_unique_tshirt_id):
    """
    Synchronizes the official 165 members into the database.
    Works identically across local SQLite and deployed PostgreSQL.
    """
    planned = get_planned_roster()
    created = 0
    updated = 0

    # Ensure placeholder test record is removed
    tarun = TShirt.query.filter_by(id="TSH0000001").first()
    if tarun:
        db.session.delete(tarun)
        db.session.commit()

    for item in planned:
        name = item["name"]
        slug = item["slug"]

        existing = TShirt.query.filter((TShirt.member_name == name) | (TShirt.slug == slug)).first()
        if existing:
            existing.member_name = name
            existing.slug = slug
            existing.member_role = "MEMBER"
            existing.member_message = "Official Association Member. Scan anytime to connect!"
            existing.member_phone = None
            existing.accent_color = "#dc2626"
            existing.member_email = "abc@gmail.com"
            db.session.add(existing)
            updated += 1
        else:
            # Custom ID preserved if Aditya Falor, otherwise unique TS ID
            tshirt_id = "25BCON1655" if name == "Aditya Falor" else generate_unique_tshirt_id()
            # If 25BCON1655 already used by someone else, generate
            if TShirt.query.get(tshirt_id):
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
            created += 1

    db.session.commit()
    return created, updated

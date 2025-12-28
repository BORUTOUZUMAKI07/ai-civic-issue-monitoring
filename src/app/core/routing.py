# Ward to Engineer Mapping
# This can be moved to a database or environment variables in a real production system.

WARD_ENGINEERS = {
    "Ward-1 (Old City/Nyay Mandir)": {"name": "Arjun Patel", "email": "ward1.engineer@vmc.gov.in"},
    "Ward-2 (Harni/Warasia)": {"name": "Sneha Sharma", "email": "ward2.engineer@vmc.gov.in"},
    "Ward-3 (Waghodia Road)": {"name": "Rajesh Mehta", "email": "ward3.engineer@vmc.gov.in"},
    "Ward-4 (Pratapnagar/Makarpura Road)": {"name": "Anita Desai", "email": "ward4.engineer@vmc.gov.in"},
    "Ward-5 (Raopura/Sayajigunj)": {"name": "Vikram Singh", "email": "ward5.engineer@vmc.gov.in"},
    "Ward-6 (Akota/OP Road)": {"name": "Priyanka Shah", "email": "ward6.engineer@vmc.gov.in"},
    "Ward-7 (Fatehgunj/Nizampura)": {"name": "Sanjay Rao", "email": "ward7.engineer@vmc.gov.in"},
    "Ward-8 (Nagarwada/Karelibaug)": {"name": "Mehul Joshi", "email": "ward8.engineer@vmc.gov.in"},
    "Ward-9 (Ajwa Road)": {"name": "Kavita Reddy", "email": "ward9.engineer@vmc.gov.in"},
    "Ward-10 (Subhanpura/Gotri)": {"name": "Deepak Varma", "email": "ward10.engineer@vmc.gov.in"},
    "Ward-11 (Vasna/Atladra)": {"name": "Rohan Mistry", "email": "ward11.engineer@vmc.gov.in"},
    "Ward-12 (Makarpura GIDC)": {"name": "Hardik Parikh", "email": "ward12.engineer@vmc.gov.in"},
    "Ward-13 (Chhani/Karodiya)": {"name": "Bhavna Patel", "email": "ward13.engineer@vmc.gov.in"},
    "Ward-14 (New VIP Road/Harni)": {"name": "Tushar Gupta", "email": "ward14.engineer@vmc.gov.in"},
    "Ward-15 (Sama)": {"name": "Jignesh Solanki", "email": "ward15.engineer@vmc.gov.in"},
    "Ward-16 (Sayajipura)": {"name": "Pooja Trivedi", "email": "ward16.engineer@vmc.gov.in"},
    "Ward-17 (Gorwa)": {"name": "Manish Khare", "email": "ward17.engineer@vmc.gov.in"},
    "Ward-18 (Bapod)": {"name": "Rakesh Amin", "email": "ward18.engineer@vmc.gov.in"},
    "Ward-19 (Dasharath)": {"name": "Sunita Bhagat", "email": "ward19.engineer@vmc.gov.in"},
}

def get_engineer_for_ward(ward_name: str) -> dict:
    return WARD_ENGINEERS.get(ward_name, {"name": "General Maintenance", "email": "civic.issues@vmc.gov.in"})

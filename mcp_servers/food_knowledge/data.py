CITIES = {
    "jaipur": {
        "name": "Jaipur",
        "region": "Rajasthan",
        "cuisines": ["rajasthani", "street_food", "north_indian"],
        "popular_dishes": ["dal_baati_churma", "pyaaz_kachori", "mirchi_bada", "ghevar", "rajasthani_thali"]
    },
    "ahmedabad": {
        "name": "Ahmedabad",
        "region": "Gujarat",
        "cuisines": ["gujarati", "street_food"],
        "popular_dishes": ["dhokla", "khandvi", "fafda", "jalebi", "thepla"]
    },
    "mumbai": {
        "name": "Mumbai",
        "region": "Maharashtra",
        "cuisines": ["street_food", "maharashtrian", "north_indian"],
        "popular_dishes": ["vada_pav", "pav_bhaji", "pani_puri", "misal_pav"]
    },
    "delhi": {
        "name": "Delhi",
        "region": "NCR",
        "cuisines": ["north_indian", "street_food"],
        "popular_dishes": ["chole_bhature", "butter_chicken", "chaat", "paratha"]
    }
}

CUISINES = {
    "rajasthani": {
        "name": "Rajasthani",
        "characteristics": ["spicy", "rich", "ghee-heavy"],
        "origin": "Rajasthan",
        "dishes": ["dal_baati_churma", "pyaaz_kachori", "mirchi_bada", "ghevar", "rajasthani_thali"]
    },
    "gujarati": {
        "name": "Gujarati",
        "characteristics": ["sweet-and-salty", "light", "vegetarian"],
        "origin": "Gujarat",
        "dishes": ["dhokla", "khandvi", "fafda", "jalebi", "thepla"]
    },
    "north_indian": {
        "name": "North Indian",
        "characteristics": ["rich", "creamy", "spicy"],
        "origin": "North India",
        "dishes": ["chole_bhature", "butter_chicken", "dal_makhani"]
    },
    "street_food": {
        "name": "Street Food",
        "characteristics": ["spicy", "tangy", "quick", "snack"],
        "origin": "Pan-India",
        "dishes": ["vada_pav", "pav_bhaji", "pani_puri", "chaat", "pyaaz_kachori"]
    }
}

DISHES = {
    "dal_baati_churma": {
        "name": "Dal Baati Churma",
        "cuisine": "rajasthani",
        "type": "main_course",
        "description": "Hard wheat rolls served with spicy lentil curry and sweet crumbled wheat."
    },
    "pyaaz_kachori": {
        "name": "Pyaaz Kachori",
        "cuisine": "rajasthani",
        "type": "snack",
        "description": "Deep-fried pastry stuffed with spicy onion filling."
    },
    "mirchi_bada": {
        "name": "Mirchi Bada",
        "cuisine": "rajasthani",
        "type": "snack",
        "description": "Large green chili stuffed with potato filling and deep-fried in gram flour batter."
    },
    "ghevar": {
        "name": "Ghevar",
        "cuisine": "rajasthani",
        "type": "dessert",
        "description": "Disc-shaped sweet made from oil, flour, and sugar syrup."
    },
    "rajasthani_thali": {
        "name": "Rajasthani Thali",
        "cuisine": "rajasthani",
        "type": "meal",
        "description": "A grand platter containing assorted Rajasthani curries, breads, and sweets."
    },
    "dhokla": {
        "name": "Dhokla",
        "cuisine": "gujarati",
        "type": "snack",
        "description": "Savory steamed cake made from fermented batter of rice and split chickpeas."
    },
    "khandvi": {
        "name": "Khandvi",
        "cuisine": "gujarati",
        "type": "snack",
        "description": "Soft, tightly rolled bite-sized pieces made of gram flour and yogurt."
    },
    "fafda": {
        "name": "Fafda",
        "cuisine": "gujarati",
        "type": "snack",
        "description": "Crispy fried snack made from gram flour, often eaten with Jalebi."
    },
    "jalebi": {
        "name": "Jalebi",
        "cuisine": "gujarati",
        "type": "dessert",
        "description": "Deep-fried spiral shape soaked in sugar syrup."
    },
    "thepla": {
        "name": "Thepla",
        "cuisine": "gujarati",
        "type": "bread/snack",
        "description": "Flatbread made from whole wheat flour, gram flour, and fenugreek leaves."
    },
    "vada_pav": {
        "name": "Vada Pav",
        "cuisine": "street_food",
        "type": "snack",
        "description": "Deep-fried potato dumpling placed inside a bread bun."
    },
    "pav_bhaji": {
        "name": "Pav Bhaji",
        "cuisine": "street_food",
        "type": "meal",
        "description": "Thick vegetable curry served with a soft bread roll."
    },
    "pani_puri": {
        "name": "Pani Puri",
        "cuisine": "street_food",
        "type": "snack",
        "description": "Hollow, crispy-fried puffed ball filled with potato, chickpeas, onions, and flavored water."
    },
    "misal_pav": {
        "name": "Misal Pav",
        "cuisine": "maharashtrian",
        "type": "meal",
        "description": "Spicy curry made of sprouted moth beans served with bread."
    },
    "chole_bhature": {
        "name": "Chole Bhature",
        "cuisine": "north_indian",
        "type": "meal",
        "description": "Spicy white chickpeas served with fried bread."
    },
    "butter_chicken": {
        "name": "Butter Chicken",
        "cuisine": "north_indian",
        "type": "main_course",
        "description": "Chicken cooked in a mildly spiced tomato sauce."
    },
    "chaat": {
        "name": "Chaat",
        "cuisine": "street_food",
        "type": "snack",
        "description": "Savory snack, typically served at road-side tracks from stalls or food carts in India."
    },
    "paratha": {
        "name": "Paratha",
        "cuisine": "north_indian",
        "type": "bread",
        "description": "Flat, thick piece of unleavened bread fried on a griddle."
    }
}

WEATHER_ASSOCIATIONS = {
    "clear": ["pani_puri", "chaat", "dhokla", "khandvi", "thepla"],
    "sunny": ["pani_puri", "chaat", "dhokla", "khandvi", "thepla"],
    "pleasant": ["chaat", "pani_puri", "dhokla", "khandvi", "thepla", "pav_bhaji"],
    "cloudy": ["pav_bhaji", "thepla", "chaat", "chole_bhature", "paratha"],
    "rainy": ["pyaaz_kachori", "mirchi_bada", "vada_pav", "fafda", "jalebi"],
    "stormy": ["pyaaz_kachori", "mirchi_bada", "vada_pav", "fafda", "jalebi", "chai"],
    "hot": ["pani_puri", "chaat", "dhokla"],
    "cold": ["dal_baati_churma", "butter_chicken", "misal_pav", "chole_bhature", "pav_bhaji"]
}

MOOD_ASSOCIATIONS = {
    "comfort": ["dal_baati_churma", "butter_chicken", "rajasthani_thali", "pav_bhaji", "chole_bhature"],
    "spicy": ["mirchi_bada", "misal_pav", "vada_pav", "pyaaz_kachori"],
    "light": ["dhokla", "khandvi"],
    "healthy": ["dhokla", "khandvi"]
}

// Master data for Nakshatras (27 Lunar Mansions)
export interface Nakshatra {
  id: string;
  name: string;
  sanskritName: string;
  hindiName: string;
  alternativeNames: string[];
  lord: string; // Ruling planet
  deity: string; // Presiding deity
  symbol: string;
}

export const nakshatras: Nakshatra[] = [
  {
    id: 'nak-1',
    name: 'Ashwini',
    sanskritName: 'अश्विनी',
    hindiName: 'अश्विनी',
    alternativeNames: ['Aswini', 'Ashvini'],
    lord: 'Ketu',
    deity: 'Ashwini Kumaras',
    symbol: 'Horse Head'
  },
  {
    id: 'nak-2',
    name: 'Bharani',
    sanskritName: 'भरणी',
    hindiName: 'भरणी',
    alternativeNames: ['Bharani'],
    lord: 'Venus',
    deity: 'Yama',
    symbol: 'Yoni'
  },
  {
    id: 'nak-3',
    name: 'Krittika',
    sanskritName: 'कृत्तिका',
    hindiName: 'कृत्तिका',
    alternativeNames: ['Karthika', 'Krithika', 'Karthigai'],
    lord: 'Sun',
    deity: 'Agni',
    symbol: 'Knife/Razor'
  },
  {
    id: 'nak-4',
    name: 'Rohini',
    sanskritName: 'रोहिणी',
    hindiName: 'रोहिणी',
    alternativeNames: ['Rohini'],
    lord: 'Moon',
    deity: 'Brahma',
    symbol: 'Cart/Chariot'
  },
  {
    id: 'nak-5',
    name: 'Mrigashira',
    sanskritName: 'मृगशिरा',
    hindiName: 'मृगशिरा',
    alternativeNames: ['Mrigashirsha', 'Margashirsha', 'Mrigasira'],
    lord: 'Mars',
    deity: 'Soma',
    symbol: 'Deer Head'
  },
  {
    id: 'nak-6',
    name: 'Ardra',
    sanskritName: 'आर्द्रा',
    hindiName: 'आर्द्रा',
    alternativeNames: ['Ardra', 'Thiruvadirai'],
    lord: 'Rahu',
    deity: 'Rudra',
    symbol: 'Teardrop'
  },
  {
    id: 'nak-7',
    name: 'Punarvasu',
    sanskritName: 'पुनर्वसु',
    hindiName: 'पुनर्वसु',
    alternativeNames: ['Punarvasu', 'Punartham'],
    lord: 'Jupiter',
    deity: 'Aditi',
    symbol: 'Bow & Quiver'
  },
  {
    id: 'nak-8',
    name: 'Pushya',
    sanskritName: 'पुष्य',
    hindiName: 'पुष्य',
    alternativeNames: ['Poosam', 'Pooyam', 'Pushyami'],
    lord: 'Saturn',
    deity: 'Brihaspati',
    symbol: 'Flower/Circle'
  },
  {
    id: 'nak-9',
    name: 'Ashlesha',
    sanskritName: 'आश्लेषा',
    hindiName: 'आश्लेषा',
    alternativeNames: ['Ayilyam', 'Ashlesha'],
    lord: 'Mercury',
    deity: 'Sarpa',
    symbol: 'Serpent'
  },
  {
    id: 'nak-10',
    name: 'Magha',
    sanskritName: 'मघा',
    hindiName: 'मघा',
    alternativeNames: ['Makam', 'Magham'],
    lord: 'Ketu',
    deity: 'Pitris',
    symbol: 'Royal Throne'
  },
  {
    id: 'nak-11',
    name: 'Purva Phalguni',
    sanskritName: 'पूर्व फाल्गुनी',
    hindiName: 'पूर्व फाल्गुनी',
    alternativeNames: ['Pooram', 'Puram', 'Purva Phalguni'],
    lord: 'Venus',
    deity: 'Bhaga',
    symbol: 'Front legs of bed'
  },
  {
    id: 'nak-12',
    name: 'Uttara Phalguni',
    sanskritName: 'उत्तर फाल्गुनी',
    hindiName: 'उत्तर फाल्गुनी',
    alternativeNames: ['Uthram', 'Uthiram', 'Uttara Phalguni'],
    lord: 'Sun',
    deity: 'Aryaman',
    symbol: 'Back legs of bed'
  },
  {
    id: 'nak-13',
    name: 'Hasta',
    sanskritName: 'हस्त',
    hindiName: 'हस्त',
    alternativeNames: ['Hastam', 'Hastha'],
    lord: 'Moon',
    deity: 'Savitar',
    symbol: 'Hand'
  },
  {
    id: 'nak-14',
    name: 'Chitra',
    sanskritName: 'चित्रा',
    hindiName: 'चित्रा',
    alternativeNames: ['Chithirai', 'Chithira'],
    lord: 'Mars',
    deity: 'Vishwakarma',
    symbol: 'Bright Jewel'
  },
  {
    id: 'nak-15',
    name: 'Swati',
    sanskritName: 'स्वाती',
    hindiName: 'स्वाती',
    alternativeNames: ['Chothi', 'Swathi'],
    lord: 'Rahu',
    deity: 'Vayu',
    symbol: 'Coral/Sword'
  },
  {
    id: 'nak-16',
    name: 'Vishakha',
    sanskritName: 'विशाखा',
    hindiName: 'विशाखा',
    alternativeNames: ['Vishakam', 'Visakam'],
    lord: 'Jupiter',
    deity: 'Indragni',
    symbol: 'Triumphal Arch'
  },
  {
    id: 'nak-17',
    name: 'Anuradha',
    sanskritName: 'अनुराधा',
    hindiName: 'अनुराधा',
    alternativeNames: ['Thriketta', 'Anizham'],
    lord: 'Saturn',
    deity: 'Mitra',
    symbol: 'Lotus'
  },
  {
    id: 'nak-18',
    name: 'Jyeshtha',
    sanskritName: 'ज्येष्ठा',
    hindiName: 'ज्येष्ठा',
    alternativeNames: ['Ketta', 'Kettai'],
    lord: 'Mercury',
    deity: 'Indra',
    symbol: 'Earring/Umbrella'
  },
  {
    id: 'nak-19',
    name: 'Mula',
    sanskritName: 'मूला',
    hindiName: 'मूला',
    alternativeNames: ['Moolam', 'Moola'],
    lord: 'Ketu',
    deity: 'Nirriti',
    symbol: 'Tied bunch of roots'
  },
  {
    id: 'nak-20',
    name: 'Purva Ashadha',
    sanskritName: 'पूर्व आषाढा',
    hindiName: 'पूर्व आषाढा',
    alternativeNames: ['Pooradam', 'Purva Ashada'],
    lord: 'Venus',
    deity: 'Apas',
    symbol: 'Elephant tusk'
  },
  {
    id: 'nak-21',
    name: 'Uttara Ashadha',
    sanskritName: 'उत्तर आषाढा',
    hindiName: 'उत्तर आषाढा',
    alternativeNames: ['Uthradam', 'Uthiradam', 'Uttara Ashada'],
    lord: 'Sun',
    deity: 'Vishvedevas',
    symbol: 'Elephant tusk'
  },
  {
    id: 'nak-22',
    name: 'Shravana',
    sanskritName: 'श्रवण',
    hindiName: 'श्रवण',
    alternativeNames: ['Thiruvonam', 'Onam', 'Shravan'],
    lord: 'Moon',
    deity: 'Vishnu',
    symbol: 'Three footprints/Ear'
  },
  {
    id: 'nak-23',
    name: 'Dhanishta',
    sanskritName: 'धनिष्ठा',
    hindiName: 'धनिष्ठा',
    alternativeNames: ['Avittam', 'Dhanishta'],
    lord: 'Mars',
    deity: 'Vasus',
    symbol: 'Drum/Flute'
  },
  {
    id: 'nak-24',
    name: 'Shatabhisha',
    sanskritName: 'शतभिषा',
    hindiName: 'शतभिषा',
    alternativeNames: ['Chathayam', 'Sathayam', 'Shatabhisha'],
    lord: 'Rahu',
    deity: 'Varuna',
    symbol: 'Empty circle'
  },
  {
    id: 'nak-25',
    name: 'Purva Bhadrapada',
    sanskritName: 'पूर्व भाद्रपद',
    hindiName: 'पूर्व भाद्रपद',
    alternativeNames: ['Poorattadhi', 'Purva Bhadra'],
    lord: 'Jupiter',
    deity: 'Aja Ekapada',
    symbol: 'Front of funeral cot'
  },
  {
    id: 'nak-26',
    name: 'Uttara Bhadrapada',
    sanskritName: 'उत्तर भाद्रपद',
    hindiName: 'उत्तर भाद्रपद',
    alternativeNames: ['Uthrittadhi', 'Uthrattadhi', 'Uttara Bhadra'],
    lord: 'Saturn',
    deity: 'Ahir Budhnya',
    symbol: 'Back of funeral cot'
  },
  {
    id: 'nak-27',
    name: 'Revati',
    sanskritName: 'रेवती',
    hindiName: 'रेवती',
    alternativeNames: ['Revati', 'Yevathi'],
    lord: 'Mercury',
    deity: 'Pushan',
    symbol: 'Fish/Pair of fish'
  }
];

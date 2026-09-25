// Master database for Gotra (Lineage Clans)
export interface Gotra {
  id: string;
  name: string;
  nameHindi: string;
  nameTamil?: string;
  nameTelugu?: string;
  nameKannada?: string;
  nameMalayalam?: string;
  aliases: string[]; // Common spelling variations
  pravara: string; // Sacred lineage
  rishi: string; // Originating sage
  description?: string;
}

export const gotras: Gotra[] = [
  { id: '1', name: 'Kashyapa', nameHindi: 'कश्यप', nameTamil: 'கசியப', nameTelugu: 'కశ్యప', nameKannada: 'ಕಶ್ಯಪ', nameMalayalam: 'കശ്യപ', aliases: ['Kashyap', 'Kashyapa', 'Kashyapam', 'Kashyapasa'], pravara: 'Kashyapa, Aghamarshana, Naidhruva', rishi: 'Sage Kashyapa', description: 'One of the most common gotras, descended from Sage Kashyapa' },
  { id: '2', name: 'Bharadwaj', nameHindi: 'भरद्वाज', nameTamil: 'பரத்வாஜ', nameTelugu: 'భరద్వాజ', nameKannada: 'ಭರದ್ವಾಜ', nameMalayalam: 'ഭരദ്വാജ്', aliases: ['Bharadwaja', 'Bharathwaj', 'Bhardwaj', 'Bharadwaja'], pravara: 'Angirasa, Bharhaspatya, Bharadwaja', rishi: 'Sage Bharadwaja', description: 'Descended from Sage Bharadwaja, common in North India' },
  { id: '3', name: 'Vashishtha', nameHindi: 'वशिष्ठ', nameTamil: 'வசிட்ட', nameTelugu: 'వశిష్ఠ', nameKannada: 'ವಶಿಷ್ಠ', nameMalayalam: 'വശിഷ്ഠ', aliases: ['Vasishtha', 'Vasishta', 'Washishtha', 'Vasist'], pravara: 'Vashishtha, Indrapramada, Abhipraraja', rishi: 'Sage Vashishtha', description: 'One of the Saptarishis, common across India' },
  { id: '4', name: 'Atri', nameHindi: 'अत्रि', nameTamil: 'அத்திரி', nameTelugu: 'అత్రి', nameKannada: 'ಅತ್ರಿ', nameMalayalam: 'അത്രി', aliases: ['Athri', 'Aathri'], pravara: 'Atri, Arcananas, Aloya', rishi: 'Sage Atri', description: 'Descended from Sage Atri, one of the Saptarishis' },
  { id: '5', name: 'Angirasa', nameHindi: 'आंगिरस', nameTamil: 'ஆங்கிரச', nameTelugu: 'ఆంగిరస', nameKannada: 'ಆಂಗಿರಸ', nameMalayalam: 'ആംഗിരസ', aliases: ['Angiras', 'Angirasas', 'Angirasa', 'Angir'], pravara: 'Angirasa, Avasyata, Trasadasyu', rishi: 'Sage Angirasa', description: 'Descended from Sage Angirasa' },
  { id: '6', name: 'Bhargava', nameHindi: 'भार्गव', nameTamil: 'பார்கவ', nameTelugu: 'భార్గవ', nameKannada: 'ಭಾರ್ಗವ', nameMalayalam: 'ഭാര്ഗവ', aliases: ['Bhargav', 'Bhargavah'], pravara: 'Bhargava, Chyavana, Apnavana', rishi: 'Sage Bhrigu', description: 'Descended from Sage Bhrigu' },
  { id: '7', name: 'Agastya', nameHindi: 'अगस्त्य', nameTamil: 'அகஸ்திய', nameTelugu: 'అగస్త్య', nameKannada: 'ಅಗಸ್ತ್ಯ', nameMalayalam: 'അഗസ്ത്യ', aliases: ['Agasthya', 'Agasti', 'Agastya'], pravara: 'Agastya, Saumavaha, Aidavalu', rishi: 'Sage Agastya', description: 'Very common in South India, especially Tamil Nadu' },
  { id: '8', name: 'Gautama', nameHindi: 'गौतम', nameTamil: 'கௌதம', nameTelugu: 'గౌతమ', nameKannada: 'ಗೌತಮ', nameMalayalam: 'ഗൗതമ', aliases: ['Gautam', 'Gotam', 'Gowtham', 'Gautama'], pravara: 'Angirasa, Ayasya, Gautama', rishi: 'Sage Gautama', description: 'Descended from Sage Gautama' },
  { id: '9', name: 'Jamadagni', nameHindi: 'जमदग्नि', nameTamil: 'ஜமதக்னி', nameTelugu: 'జమదగ్ని', nameKannada: 'ಜಮದಗ್ನಿ', nameMalayalam: 'ജമദഗ്നി', aliases: ['Jamadagni', 'Jamadagniya'], pravara: 'Bhargava, Chyavana, Jamadagni', rishi: 'Sage Jamadagni', description: 'Descended from Sage Jamadagni, father of Parashurama' },
  { id: '10', name: 'Vishwamitra', nameHindi: 'विश्वामित्र', nameTamil: 'விச்வாமித்ர', nameTelugu: 'విశ్వామిత్ర', nameKannada: 'ವಿಶ್ವಾಮಿತ್ರ', nameMalayalam: 'വിശ്വാമിത്ര', aliases: ['Vishwamitra', 'Vishvamitra', 'Viswamitra'], pravara: 'Vishwamitra, Devarata, Audalam', rishi: 'Sage Vishwamitra', description: 'Descended from Sage Vishwamitra' },
  { id: '11', name: 'Shandilya', nameHindi: 'शाण्डिल्य', nameTamil: 'சாண்டிலிய', nameTelugu: 'శాండిల్య', nameKannada: 'ಶಾಂಡಿಲ್ಯ', nameMalayalam: 'ശാണ്ടില്യ', aliases: ['Shandilya', 'Sandilya', 'Shandilya', 'Sandyal'], pravara: 'Shandilya, Aghamarshana, Naidhruva', rishi: 'Sage Shandilya', description: 'Common in North and Central India' },
  { id: '12', name: 'Parashara', nameHindi: 'पराशर', nameTamil: 'பராசர', nameTelugu: 'పరాశర', nameKannada: 'ಪರಾಶರ', nameMalayalam: 'പരാശര', aliases: ['Parashar', 'Parasar', 'Parasara'], pravara: 'Parashara, Aghamarshana, Naidhruva', rishi: 'Sage Parashara', description: 'Descended from Sage Parashara, father of Vyasa' },
  { id: '13', name: 'Kaundinya', nameHindi: 'कौण्डिन्य', nameTamil: 'கௌண்டின்ய', nameTelugu: 'కౌండిన్య', nameKannada: 'ಕೌಂಡಿನ್ಯ', nameMalayalam: 'കൗണ്ഡിന്യ', aliases: ['Kaundinya', 'Koundinya', 'Kaundinyayana'], pravara: 'Kaundinya, Vasishtha, Maitravaruna', rishi: 'Sage Kaundinya', description: 'Very common in South India' },
  { id: '14', name: 'Upamanyu', nameHindi: 'उपमन्यु', nameTamil: 'உபமன்யு', nameTelugu: 'ఉపమన్యు', nameKannada: 'ಉಪಮನ್ಯು', nameMalayalam: 'ഉപമന്യു', aliases: ['Upamanyu', 'Upamanyava'], pravara: 'Upamanyu, Vashishtha, Aupamanyava', rishi: 'Sage Upamanyu', description: 'Less common but found across India' },
  { id: '15', name: 'Garga', nameHindi: 'गर्ग', nameTamil: 'கர்க', nameTelugu: 'గర్గ', nameKannada: 'ಗರ್ಗ', nameMalayalam: 'ഗര്ഗ', aliases: ['Garga', 'Gargya'], pravara: 'Angirasa, Barhaspatya, Gargya', rishi: 'Sage Garga', description: 'Common in North India, especially among Jains' }
];

export function searchGotras(query: string): Gotra[] {
  if (!query) return [];
  const q = query.toLowerCase().trim();
  return gotras.filter(g =>
    g.name.toLowerCase().includes(q) ||
    g.nameHindi.includes(q) ||
    (g.nameTamil && g.nameTamil.includes(q)) ||
    (g.nameTelugu && g.nameTelugu.includes(q)) ||
    (g.nameKannada && g.nameKannada.includes(q)) ||
    (g.nameMalayalam && g.nameMalayalam.includes(q)) ||
    g.aliases.some(alias => alias.toLowerCase().includes(q)) ||
    g.rishi.toLowerCase().includes(q)
  );
}

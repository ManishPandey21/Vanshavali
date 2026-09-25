export interface Person {
  id: string;
  firstName: string;
  lastName: string;
  nativeName?: string; // Name in native script
  gender: 'male' | 'female';
  birthDate?: string;
  birthPlace?: string;
  deathDate?: string;
  isLiving: boolean;
  
  // Indian-specific fields
  gotra?: string;
  pravara?: string;
  kula?: string; // e.g., Suryavanshi, Chandravanshi
  jati?: string; // Caste/sub-caste
  kuladevata?: string; // Family deity
  kuladevataTemple?: string; // Temple location
  nakshatra?: string; // Birth star
  rashi?: string; // Zodiac sign
  
  // Location
  ancestralVillage?: string;
  district?: string;
  state?: string;
  
  // Matrilineal (for Kerala/Karnataka communities)
  tharavad?: string; // Ancestral house name
  
  // Relationships
  fatherId?: string;
  motherId?: string;
  spouseIds: string[];
  childrenIds: string[];
  
  // Additional
  photo?: string;
  occupation?: string;
  education?: string;
  notes?: string;
  
  // Privacy
  isPrivate: boolean;
}

export interface Family {
  id: string;
  name: string;
  gotra: string;
  kula: string;
  kuladevata: string;
  kuladevataTemple?: string;
  ancestralVillage: string;
  district: string;
  state: string;
  rootPersonId: string;
}

export interface Household {
  id: string;
  name: string;
  location: string;
  memberIds: string[];
  headId?: string;
}

export type ViewMode = 'tree' | 'cluster' | 'list' | 'relations';
export type Page = 'dashboard' | 'tree' | 'members' | 'add' | 'search' | 'gotra' | 'settings';

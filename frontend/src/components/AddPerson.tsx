import { useState } from 'react';
import { Person } from '../types';
import { ArrowLeft, Save } from 'lucide-react';

interface AddPersonProps {
  persons: Person[];
  onAdd: (person: Person) => void;
  onCancel: () => void;
}

const nakshatras = [
  'Ashwini', 'Bharani', 'Krittika', 'Rohini', 'Mrigashira', 'Ardra',
  'Punarvasu', 'Pushya', 'Ashlesha', 'Magha', 'Purva Phalguni', 'Uttara Phalguni',
  'Hasta', 'Chitra', 'Swati', 'Vishakha', 'Anuradha', 'Jyeshtha',
  'Mula', 'Purva Ashadha', 'Uttara Ashadha', 'Shravana', 'Dhanishta', 'Shatabhisha',
  'Purva Bhadrapada', 'Uttara Bhadrapada', 'Revati'
];

const rashis = [
  'Mesha (Aries)', 'Vrishabha (Taurus)', 'Mithuna (Gemini)', 'Karka (Cancer)',
  'Simha (Leo)', 'Kanya (Virgo)', 'Tula (Libra)', 'Vrischika (Scorpio)',
  'Dhanu (Sagittarius)', 'Makara (Capricorn)', 'Kumbha (Aquarius)', 'Meena (Pisces)'
];

const gotras = [
  'Kashyapa', 'Bharadwaj', 'Vashishtha', 'Atri', 'Angirasa', 'Bhargava',
  'Agastya', 'Gautama', 'Jamadagni', 'Vishwamitra'
];

export default function AddPerson({ persons, onAdd, onCancel }: AddPersonProps) {
  const [formData, setFormData] = useState({
    firstName: '',
    lastName: '',
    nativeName: '',
    gender: 'male' as 'male' | 'female',
    birthDate: '',
    birthPlace: '',
    deathDate: '',
    isLiving: true,
    gotra: '',
    kula: '',
    jati: '',
    kuladevata: '',
    kuladevataTemple: '',
    nakshatra: '',
    rashi: '',
    ancestralVillage: '',
    district: '',
    state: '',
    fatherId: '',
    motherId: '',
    occupation: '',
    education: '',
    notes: '',
    isPrivate: false
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const newPerson: Person = {
      id: `p${Date.now()}`,
      firstName: formData.firstName,
      lastName: formData.lastName,
      nativeName: formData.nativeName || undefined,
      gender: formData.gender,
      birthDate: formData.birthDate || undefined,
      birthPlace: formData.birthPlace || undefined,
      deathDate: formData.deathDate || undefined,
      isLiving: formData.isLiving,
      gotra: formData.gotra || undefined,
      kula: formData.kula || undefined,
      jati: formData.jati || undefined,
      kuladevata: formData.kuladevata || undefined,
      kuladevataTemple: formData.kuladevataTemple || undefined,
      nakshatra: formData.nakshatra || undefined,
      rashi: formData.rashi || undefined,
      ancestralVillage: formData.ancestralVillage || undefined,
      district: formData.district || undefined,
      state: formData.state || undefined,
      fatherId: formData.fatherId || undefined,
      motherId: formData.motherId || undefined,
      spouseIds: [],
      childrenIds: [],
      occupation: formData.occupation || undefined,
      education: formData.education || undefined,
      notes: formData.notes || undefined,
      isPrivate: formData.isPrivate
    };
    onAdd(newPerson);
  };

  const potentialFathers = persons.filter(p => p.gender === 'male');
  const potentialMothers = persons.filter(p => p.gender === 'female');

  return (
    <div className="p-6 max-w-4xl mx-auto">
      {/* Header */}
      <div className="flex items-center gap-4 mb-6">
        <button onClick={onCancel} className="p-2 rounded-lg hover:bg-gray-100 transition-colors">
          <ArrowLeft size={20} className="text-gray-600" />
        </button>
        <div>
          <h2 className="text-2xl font-bold text-gray-800">Add Family Member</h2>
          <p className="text-sm text-gray-500">Add a new person to the family tree with Indian cultural details</p>
        </div>
      </div>

      <form onSubmit={handleSubmit} className="space-y-6">
        {/* Basic Info */}
        <section className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm">
          <h3 className="text-lg font-semibold text-gray-800 mb-4 flex items-center gap-2">
            <span className="w-6 h-6 bg-amber-100 rounded-full flex items-center justify-center text-xs font-bold text-amber-700">1</span>
            Basic Information
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">First Name *</label>
              <input
                type="text"
                required
                value={formData.firstName}
                onChange={(e) => setFormData({...formData, firstName: e.target.value})}
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-amber-500"
                placeholder="e.g., Ramaswamy"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Last Name / Surname *</label>
              <input
                type="text"
                required
                value={formData.lastName}
                onChange={(e) => setFormData({...formData, lastName: e.target.value})}
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-amber-500"
                placeholder="e.g., Iyer"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Name in Native Script</label>
              <input
                type="text"
                value={formData.nativeName}
                onChange={(e) => setFormData({...formData, nativeName: e.target.value})}
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-amber-500"
                placeholder="e.g., रामस्वामी अय्यर"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Gender *</label>
              <select
                value={formData.gender}
                onChange={(e) => setFormData({...formData, gender: e.target.value as 'male' | 'female'})}
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-amber-500"
              >
                <option value="male">Male</option>
                <option value="female">Female</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Birth Date</label>
              <input
                type="date"
                value={formData.birthDate}
                onChange={(e) => setFormData({...formData, birthDate: e.target.value})}
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-amber-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Birth Place</label>
              <input
                type="text"
                value={formData.birthPlace}
                onChange={(e) => setFormData({...formData, birthPlace: e.target.value})}
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-amber-500"
                placeholder="e.g., Kanchipuram"
              />
            </div>
            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                id="isLiving"
                checked={formData.isLiving}
                onChange={(e) => setFormData({...formData, isLiving: e.target.checked, deathDate: e.target.checked ? '' : formData.deathDate})}
                className="w-4 h-4 text-amber-600 border-gray-300 rounded focus:ring-amber-500"
              />
              <label htmlFor="isLiving" className="text-sm text-gray-700">Currently Living</label>
            </div>
            {!formData.isLiving && (
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Death Date</label>
                <input
                  type="date"
                  value={formData.deathDate}
                  onChange={(e) => setFormData({...formData, deathDate: e.target.value})}
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-amber-500"
                />
              </div>
            )}
          </div>
        </section>

        {/* Indian Cultural Details */}
        <section className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm">
          <h3 className="text-lg font-semibold text-gray-800 mb-4 flex items-center gap-2">
            <span className="w-6 h-6 bg-purple-100 rounded-full flex items-center justify-center text-xs font-bold text-purple-700">2</span>
            Indian Cultural Details
            <span className="text-xs text-gray-500 font-normal">(Cultural markers for Indian genealogy)</span>
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Gotra (Lineage/Clan)</label>
              <select
                value={formData.gotra}
                onChange={(e) => setFormData({...formData, gotra: e.target.value})}
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-amber-500"
              >
                <option value="">Select Gotra</option>
                {gotras.map(g => <option key={g} value={g}>{g}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Kula (Dynasty)</label>
              <select
                value={formData.kula}
                onChange={(e) => setFormData({...formData, kula: e.target.value})}
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-amber-500"
              >
                <option value="">Select Kula</option>
                <option value="Suryavanshi">Suryavanshi (Solar Dynasty)</option>
                <option value="Chandravanshi">Chandravanshi (Lunar Dynasty)</option>
                <option value="Agnivanshi">Agnivanshi (Fire Dynasty)</option>
                <option value="Nagavanshi">Nagavanshi (Serpent Dynasty)</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Jati (Sub-caste)</label>
              <input
                type="text"
                value={formData.jati}
                onChange={(e) => setFormData({...formData, jati: e.target.value})}
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-amber-500"
                placeholder="e.g., Iyer (Vadama)"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Nakshatra (Birth Star)</label>
              <select
                value={formData.nakshatra}
                onChange={(e) => setFormData({...formData, nakshatra: e.target.value})}
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-amber-500"
              >
                <option value="">Select Nakshatra</option>
                {nakshatras.map(n => <option key={n} value={n}>{n}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Rashi (Zodiac Sign)</label>
              <select
                value={formData.rashi}
                onChange={(e) => setFormData({...formData, rashi: e.target.value})}
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-amber-500"
              >
                <option value="">Select Rashi</option>
                {rashis.map(r => <option key={r} value={r.split(' ')[0]}>{r}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Kuladevata (Family Deity)</label>
              <input
                type="text"
                value={formData.kuladevata}
                onChange={(e) => setFormData({...formData, kuladevata: e.target.value})}
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-amber-500"
                placeholder="e.g., Goddess Kamakshi"
              />
            </div>
            <div className="md:col-span-2">
              <label className="block text-sm font-medium text-gray-700 mb-1">Kuladevata Temple</label>
              <input
                type="text"
                value={formData.kuladevataTemple}
                onChange={(e) => setFormData({...formData, kuladevataTemple: e.target.value})}
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-amber-500"
                placeholder="e.g., Kamakshi Amman Temple, Kanchipuram"
              />
            </div>
          </div>
        </section>

        {/* Ancestral Location */}
        <section className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm">
          <h3 className="text-lg font-semibold text-gray-800 mb-4 flex items-center gap-2">
            <span className="w-6 h-6 bg-green-100 rounded-full flex items-center justify-center text-xs font-bold text-green-700">3</span>
            Ancestral Location
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Ancestral Village</label>
              <input
                type="text"
                value={formData.ancestralVillage}
                onChange={(e) => setFormData({...formData, ancestralVillage: e.target.value})}
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-amber-500"
                placeholder="e.g., Kanchipuram"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">District</label>
              <input
                type="text"
                value={formData.district}
                onChange={(e) => setFormData({...formData, district: e.target.value})}
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-amber-500"
                placeholder="e.g., Kanchipuram"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">State</label>
              <input
                type="text"
                value={formData.state}
                onChange={(e) => setFormData({...formData, state: e.target.value})}
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-amber-500"
                placeholder="e.g., Tamil Nadu"
              />
            </div>
          </div>
        </section>

        {/* Relationships */}
        <section className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm">
          <h3 className="text-lg font-semibold text-gray-800 mb-4 flex items-center gap-2">
            <span className="w-6 h-6 bg-blue-100 rounded-full flex items-center justify-center text-xs font-bold text-blue-700">4</span>
            Family Relationships
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Father</label>
              <select
                value={formData.fatherId}
                onChange={(e) => setFormData({...formData, fatherId: e.target.value})}
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-amber-500"
              >
                <option value="">Select Father</option>
                {potentialFathers.map(p => (
                  <option key={p.id} value={p.id}>{p.firstName} {p.lastName}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Mother</label>
              <select
                value={formData.motherId}
                onChange={(e) => setFormData({...formData, motherId: e.target.value})}
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-amber-500"
              >
                <option value="">Select Mother</option>
                {potentialMothers.map(p => (
                  <option key={p.id} value={p.id}>{p.firstName} {p.lastName}</option>
                ))}
              </select>
            </div>
          </div>
        </section>

        {/* Additional */}
        <section className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm">
          <h3 className="text-lg font-semibold text-gray-800 mb-4 flex items-center gap-2">
            <span className="w-6 h-6 bg-gray-100 rounded-full flex items-center justify-center text-xs font-bold text-gray-700">5</span>
            Additional Details
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Occupation</label>
              <input
                type="text"
                value={formData.occupation}
                onChange={(e) => setFormData({...formData, occupation: e.target.value})}
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-amber-500"
                placeholder="e.g., Software Engineer"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Education</label>
              <input
                type="text"
                value={formData.education}
                onChange={(e) => setFormData({...formData, education: e.target.value})}
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-amber-500"
                placeholder="e.g., B.Tech, MBA"
              />
            </div>
            <div className="md:col-span-2">
              <label className="block text-sm font-medium text-gray-700 mb-1">Notes</label>
              <textarea
                value={formData.notes}
                onChange={(e) => setFormData({...formData, notes: e.target.value})}
                rows={3}
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-amber-500 resize-none"
                placeholder="Any additional notes about this person..."
              />
            </div>
            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                id="isPrivate"
                checked={formData.isPrivate}
                onChange={(e) => setFormData({...formData, isPrivate: e.target.checked})}
                className="w-4 h-4 text-amber-600 border-gray-300 rounded focus:ring-amber-500"
              />
              <label htmlFor="isPrivate" className="text-sm text-gray-700">
                🔒 Mark as Private (hidden from non-family members)
              </label>
            </div>
          </div>
        </section>

        {/* Actions */}
        <div className="flex justify-end gap-3">
          <button
            type="button"
            onClick={onCancel}
            className="px-6 py-2 border border-gray-200 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-50 transition-colors"
          >
            Cancel
          </button>
          <button
            type="submit"
            className="flex items-center gap-2 px-6 py-2 bg-amber-700 text-white rounded-lg text-sm font-medium hover:bg-amber-800 transition-colors shadow-sm"
          >
            <Save size={16} />
            Save Member
          </button>
        </div>
      </form>
    </div>
  );
}

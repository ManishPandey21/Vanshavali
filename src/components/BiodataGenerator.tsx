import { Person } from '../types';
import { Download, Printer, ArrowLeft, Heart, Star, MapPin, Users } from 'lucide-react';
import { useState } from 'react';

interface BiodataGeneratorProps {
  person: Person;
  persons: Person[];
  onBack: () => void;
}

export default function BiodataGenerator({ person, persons, onBack }: BiodataGeneratorProps) {
  const [includePhotos, setIncludePhotos] = useState(true);
  const [includeHoroscope, setIncludeHoroscope] = useState(true);
  const [includeFamilyDetails, setIncludeFamilyDetails] = useState(true);

  const father = person.fatherId ? persons.find(p => p.id === person.fatherId) : null;
  const mother = person.motherId ? persons.find(p => p.id === person.motherId) : null;
  const siblings = persons.filter(p => {
    if (p.id === person.id) return false;
    return (person.fatherId && p.fatherId === person.fatherId) || (person.motherId && p.motherId === person.motherId);
  });

  const handlePrint = () => {
    window.print();
  };

  const handleDownload = () => {
    // In a real app, this would generate a PDF
    alert('PDF download feature would be implemented with a library like jsPDF or html2pdf.js');
  };

  return (
    <div className="p-6 max-w-4xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6 no-print">
        <div className="flex items-center gap-4">
          <button onClick={onBack} className="p-2 rounded-lg hover:bg-gray-100 transition-colors">
            <ArrowLeft size={20} className="text-gray-600" />
          </button>
          <div>
            <h2 className="text-2xl font-bold text-gray-800">Matrimonial Biodata</h2>
            <p className="text-sm text-gray-500">Generate traditional Indian matrimonial biodata</p>
          </div>
        </div>
        <div className="flex gap-2">
          <button
            onClick={handlePrint}
            className="flex items-center gap-2 px-4 py-2 bg-amber-700 text-white rounded-lg hover:bg-amber-800 transition-colors text-sm font-medium"
          >
            <Printer size={16} />
            Print
          </button>
          <button
            onClick={handleDownload}
            className="flex items-center gap-2 px-4 py-2 bg-green-700 text-white rounded-lg hover:bg-green-800 transition-colors text-sm font-medium"
          >
            <Download size={16} />
            Download PDF
          </button>
        </div>
      </div>

      {/* Options */}
      <div className="bg-white rounded-xl border border-gray-200 p-4 mb-6 no-print">
        <h3 className="text-sm font-semibold text-gray-700 mb-3">Biodata Options</h3>
        <div className="flex flex-wrap gap-4">
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={includePhotos}
              onChange={(e) => setIncludePhotos(e.target.checked)}
              className="w-4 h-4 text-amber-600 border-gray-300 rounded focus:ring-amber-500"
            />
            <span className="text-sm text-gray-700">Include Photo Placeholder</span>
          </label>
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={includeHoroscope}
              onChange={(e) => setIncludeHoroscope(e.target.checked)}
              className="w-4 h-4 text-amber-600 border-gray-300 rounded focus:ring-amber-500"
            />
            <span className="text-sm text-gray-700">Include Horoscope Details</span>
          </label>
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={includeFamilyDetails}
              onChange={(e) => setIncludeFamilyDetails(e.target.checked)}
              className="w-4 h-4 text-amber-600 border-gray-300 rounded focus:ring-amber-500"
            />
            <span className="text-sm text-gray-700">Include Family Details</span>
          </label>
        </div>
      </div>

      {/* Biodata Document */}
      <div className="bg-white border-2 border-amber-200 rounded-xl shadow-lg overflow-hidden">
        {/* Header with Om Symbol */}
        <div className="bg-gradient-to-r from-amber-600 to-orange-600 text-white p-8 text-center">
          <div className="text-4xl mb-2">ॐ</div>
          <h1 className="text-3xl font-bold mb-1">Shree Ganeshaya Namah</h1>
          <p className="text-amber-100 text-sm">॥ श्री गणेशाय नमः ॥</p>
        </div>

        {/* Personal Details */}
        <div className="p-8">
          <div className="flex gap-8 mb-8">
            {includePhotos && (
              <div className="flex-shrink-0">
                <div className={`w-32 h-40 border-2 border-amber-300 rounded-lg flex items-center justify-center ${
                  person.gender === 'male' ? 'bg-blue-50' : 'bg-pink-50'
                }`}>
                  <div className={`w-20 h-20 rounded-full flex items-center justify-center text-white text-3xl font-bold ${
                    person.gender === 'male' ? 'bg-blue-500' : 'bg-pink-500'
                  }`}>
                    {person.firstName[0]}
                  </div>
                </div>
                <p className="text-xs text-center text-gray-500 mt-2">Photo</p>
              </div>
            )}
            <div className="flex-1">
              <h2 className="text-2xl font-bold text-gray-800 mb-4 border-b-2 border-amber-200 pb-2">
                Personal Details
              </h2>
              <div className="grid grid-cols-2 gap-3">
                <DetailRow label="Name" value={`${person.firstName} ${person.lastName}`} />
                {person.nativeName && <DetailRow label="Name (Native)" value={person.nativeName} />}
                <DetailRow label="Date of Birth" value={person.birthDate || 'Not specified'} />
                <DetailRow label="Place of Birth" value={person.birthPlace || 'Not specified'} />
                <DetailRow label="Gender" value={person.gender === 'male' ? 'Male' : 'Female'} />
                <DetailRow label="Marital Status" value="Unmarried" />
              </div>
            </div>
          </div>

          {/* Horoscope Details */}
          {includeHoroscope && (
            <div className="mb-8">
              <h2 className="text-xl font-bold text-gray-800 mb-4 border-b-2 border-amber-200 pb-2 flex items-center gap-2">
                <Star size={20} className="text-amber-600" />
                Horoscope Details
              </h2>
              <div className="grid grid-cols-2 gap-3">
                <DetailRow label="Gotra" value={person.gotra || 'Not specified'} />
                <DetailRow label="Kula" value={person.kula || 'Not specified'} />
                <DetailRow label="Nakshatra" value={person.nakshatra || 'Not specified'} />
                <DetailRow label="Rashi" value={person.rashi || 'Not specified'} />
                <DetailRow label="Kuladevata" value={person.kuladevata || 'Not specified'} />
                {person.pravara && <DetailRow label="Pravara" value={person.pravara} />}
              </div>
            </div>
          )}

          {/* Education & Profession */}
          <div className="mb-8">
            <h2 className="text-xl font-bold text-gray-800 mb-4 border-b-2 border-amber-200 pb-2">
              Education & Profession
            </h2>
            <div className="grid grid-cols-2 gap-3">
              <DetailRow label="Education" value={person.education || 'Not specified'} />
              <DetailRow label="Occupation" value={person.occupation || 'Not specified'} />
              <DetailRow label="Annual Income" value="Not specified" />
            </div>
          </div>

          {/* Family Details */}
          {includeFamilyDetails && (
            <div className="mb-8">
              <h2 className="text-xl font-bold text-gray-800 mb-4 border-b-2 border-amber-200 pb-2 flex items-center gap-2">
                <Users size={20} className="text-amber-600" />
                Family Details
              </h2>
              <div className="grid grid-cols-2 gap-3">
                {father && <DetailRow label="Father's Name" value={`${father.firstName} ${father.lastName}`} />}
                {father?.occupation && <DetailRow label="Father's Occupation" value={father.occupation} />}
                {mother && <DetailRow label="Mother's Name" value={`${mother.firstName} ${mother.lastName}`} />}
                {mother?.occupation && <DetailRow label="Mother's Occupation" value={mother.occupation} />}
                <DetailRow label="Siblings" value={
                  siblings.length > 0 
                    ? siblings.map(s => `${s.firstName} (${s.gender === 'male' ? 'Brother' : 'Sister'})`).join(', ')
                    : 'Not specified'
                } />
                <DetailRow label="Family Type" value="Joint Family" />
                <DetailRow label="Family Status" value="Middle Class" />
              </div>
            </div>
          )}

          {/* Ancestral Details */}
          <div className="mb-8">
            <h2 className="text-xl font-bold text-gray-800 mb-4 border-b-2 border-amber-200 pb-2 flex items-center gap-2">
              <MapPin size={20} className="text-amber-600" />
              Ancestral Details
            </h2>
            <div className="grid grid-cols-2 gap-3">
              <DetailRow label="Ancestral Village" value={person.ancestralVillage || 'Not specified'} />
              <DetailRow label="District" value={person.district || 'Not specified'} />
              <DetailRow label="State" value={person.state || 'Not specified'} />
              <DetailRow label="Kuladevata Temple" value={person.kuladevataTemple || 'Not specified'} />
            </div>
          </div>

          {/* Contact Details */}
          <div className="mb-8">
            <h2 className="text-xl font-bold text-gray-800 mb-4 border-b-2 border-amber-200 pb-2">
              Contact Details
            </h2>
            <div className="grid grid-cols-2 gap-3">
              <DetailRow label="Contact Number" value="+91 XXXXX XXXXX" />
              <DetailRow label="Email" value="email@example.com" />
              <DetailRow label="Address" value="Current address not specified" />
            </div>
          </div>

          {/* Expectations */}
          <div>
            <h2 className="text-xl font-bold text-gray-800 mb-4 border-b-2 border-amber-200 pb-2 flex items-center gap-2">
              <Heart size={20} className="text-red-600" />
              Expectations
            </h2>
            <p className="text-sm text-gray-700 leading-relaxed">
              Looking for a suitable match from a good family background with similar cultural values. 
              The prospective partner should be well-educated and from the same caste but different Gotra. 
              Horoscope matching is preferred.
            </p>
          </div>
        </div>

        {/* Footer */}
        <div className="bg-amber-50 border-t-2 border-amber-200 p-4 text-center">
          <p className="text-xs text-amber-800">
            ॥ शुभम भवतु ॥ | May there be auspiciousness | Generated from Vanshavali Family Tree
          </p>
        </div>
      </div>
    </div>
  );
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs text-gray-500 uppercase tracking-wider">{label}</p>
      <p className="text-sm text-gray-800 font-medium">{value}</p>
    </div>
  );
}

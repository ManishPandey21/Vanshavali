import { Person } from '../types';
import { ArrowLeft, MapPin, Star, Heart, Users, Calendar, BookOpen, Shield } from 'lucide-react';

interface PersonDetailProps {
  person: Person;
  persons: Person[];
  onBack: () => void;
  onSelectPerson: (person: Person) => void;
  onGenerateBiodata?: (person: Person) => void;
}

export default function PersonDetail({ person, persons, onBack, onSelectPerson, onGenerateBiodata }: PersonDetailProps) {
  const father = person.fatherId ? persons.find(p => p.id === person.fatherId) : null;
  const mother = person.motherId ? persons.find(p => p.id === person.motherId) : null;
  const spouses = person.spouseIds.map(id => persons.find(p => p.id === id)).filter(Boolean) as Person[];
  const children = person.childrenIds.map(id => persons.find(p => p.id === id)).filter(Boolean) as Person[];
  const siblings = persons.filter(p => {
    if (p.id === person.id) return false;
    return (person.fatherId && p.fatherId === person.fatherId) || (person.motherId && p.motherId === person.motherId);
  });

  // Extended relationships
  const grandparents = persons.filter(p => {
    if (father && (father.fatherId === p.id || father.motherId === p.id)) return true;
    if (mother && (mother.fatherId === p.id || mother.motherId === p.id)) return true;
    return false;
  });

  const grandchildren = persons.filter(p => {
    return children.some(c => p.fatherId === c.id || p.motherId === c.id);
  });

  const unclesAunts = persons.filter(p => {
    if (father && father.fatherId && (p.fatherId === father.fatherId) && p.id !== father.id) return true;
    if (mother && mother.fatherId && (p.fatherId === mother.fatherId) && p.id !== mother.id) return true;
    return false;
  });

  const nephewsNieces = persons.filter(p => {
    return siblings.some(s => p.fatherId === s.id || p.motherId === s.id);
  });

  const cousins = persons.filter(p => {
    return unclesAunts.some(ua => p.fatherId === ua.id || p.motherId === ua.id);
  });

  // In-laws
  const inLaws: { person: Person; label: string }[] = [];
  if (spouses.length > 0) {
    const spouse = spouses[0];
    const spouseFather = spouse.fatherId ? persons.find(p => p.id === spouse.fatherId) : null;
    const spouseMother = spouse.motherId ? persons.find(p => p.id === spouse.motherId) : null;
    if (spouseFather) inLaws.push({ person: spouseFather, label: 'Father-in-law' });
    if (spouseMother) inLaws.push({ person: spouseMother, label: 'Mother-in-law' });
    
    // Spouse's siblings
    const spouseSiblings = persons.filter(p => {
      if (p.id === spouse.id) return false;
      return (spouse.fatherId && p.fatherId === spouse.fatherId) || (spouse.motherId && p.motherId === spouse.motherId);
    });
    spouseSiblings.forEach(ss => {
      inLaws.push({ person: ss, label: ss.gender === 'male' ? 'Brother-in-law' : 'Sister-in-law' });
    });

    // Siblings' spouses
    siblings.forEach(sib => {
      sib.spouseIds.forEach(spId => {
        const sp = persons.find(p => p.id === spId);
        if (sp) {
          inLaws.push({ person: sp, label: sp.gender === 'male' ? 'Brother-in-law' : 'Sister-in-law' });
        }
      });
    });

    // Children's spouses
    children.forEach(child => {
      child.spouseIds.forEach(spId => {
        const sp = persons.find(p => p.id === spId);
        if (sp) {
          inLaws.push({ person: sp, label: sp.gender === 'male' ? 'Son-in-law (Damad)' : 'Daughter-in-law (Bahu)' });
        }
      });
    });
  }

  return (
    <div className="p-6 max-w-5xl mx-auto">
      {/* Back Button */}
      <button onClick={onBack} className="flex items-center gap-2 text-gray-600 hover:text-gray-800 mb-6 transition-colors">
        <ArrowLeft size={18} />
        <span className="text-sm font-medium">Back to Family Tree</span>
      </button>

      {/* Profile Header */}
      <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden mb-6">
        <div className="bg-gradient-to-r from-amber-700 to-orange-700 h-32 relative">
          <div className="absolute inset-0 opacity-10">
            <svg viewBox="0 0 400 100" className="w-full h-full">
              <pattern id="pattern" x="0" y="0" width="50" height="50" patternUnits="userSpaceOnUse">
                <circle cx="25" cy="25" r="20" fill="none" stroke="white" strokeWidth="0.5" />
              </pattern>
              <rect width="400" height="100" fill="url(#pattern)" />
            </svg>
          </div>
        </div>
        <div className="px-6 pb-6 -mt-12">
          <div className="flex items-end gap-4">
            <div className={`w-24 h-24 rounded-2xl flex items-center justify-center text-white text-3xl font-bold border-4 border-white shadow-lg ${
              person.gender === 'male' ? 'bg-blue-500' : 'bg-pink-500'
            }`}>
              {person.firstName[0]}
            </div>
            <div className="flex-1 pb-1">
              <h1 className="text-2xl font-bold text-gray-800">{person.firstName} {person.lastName}</h1>
              {person.nativeName && (
                <p className="text-sm text-gray-500">{person.nativeName}</p>
              )}
              <div className="flex flex-wrap gap-2 mt-2">
                {person.gotra && (
                  <span className="text-xs bg-amber-100 text-amber-800 px-2 py-1 rounded-full font-medium">
                    {person.gotra} Gotra
                  </span>
                )}
                {person.jati && (
                  <span className="text-xs bg-purple-100 text-purple-800 px-2 py-1 rounded-full">
                    {person.jati}
                  </span>
                )}
                <span className={`text-xs px-2 py-1 rounded-full ${
                  person.isLiving ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-600'
                }`}>
                  {person.isLiving ? '● Living' : '✝ Deceased'}
                </span>
                {person.isPrivate && (
                  <span className="text-xs bg-red-100 text-red-700 px-2 py-1 rounded-full">🔒 Private</span>
                )}
              </div>
            </div>
            {onGenerateBiodata && person.isLiving && (
              <button
                onClick={() => onGenerateBiodata(person)}
                className="flex items-center gap-2 px-4 py-2 bg-green-700 text-white rounded-lg hover:bg-green-800 transition-colors text-sm font-medium shadow-sm"
              >
                📋 Generate Biodata
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Details Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column - Main Info */}
        <div className="lg:col-span-2 space-y-6">
          {/* Birth & Life */}
          <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
            <h3 className="font-semibold text-gray-800 mb-3 flex items-center gap-2">
              <Calendar size={18} className="text-blue-600" />
              Life Events
            </h3>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <p className="text-xs text-gray-500 uppercase tracking-wider">Born</p>
                <p className="text-sm text-gray-800 font-medium">
                  {person.birthDate || 'Unknown'} {person.birthPlace && `• ${person.birthPlace}`}
                </p>
              </div>
              {!person.isLiving && (
                <div>
                  <p className="text-xs text-gray-500 uppercase tracking-wider">Passed Away</p>
                  <p className="text-sm text-gray-800 font-medium">{person.deathDate || 'Unknown'}</p>
                </div>
              )}
              {person.occupation && (
                <div>
                  <p className="text-xs text-gray-500 uppercase tracking-wider">Occupation</p>
                  <p className="text-sm text-gray-800 font-medium">{person.occupation}</p>
                </div>
              )}
              {person.education && (
                <div>
                  <p className="text-xs text-gray-500 uppercase tracking-wider">Education</p>
                  <p className="text-sm text-gray-800 font-medium">{person.education}</p>
                </div>
              )}
            </div>
          </div>

          {/* Astrological Data */}
          <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
            <h3 className="font-semibold text-gray-800 mb-3 flex items-center gap-2">
              <Star size={18} className="text-amber-600" />
              Astrological Data (Jyotish)
            </h3>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="bg-amber-50 rounded-lg p-3 text-center">
                <p className="text-xs text-amber-600 font-medium">Nakshatra</p>
                <p className="text-sm text-gray-800 font-semibold mt-1">{person.nakshatra || '—'}</p>
              </div>
              <div className="bg-purple-50 rounded-lg p-3 text-center">
                <p className="text-xs text-purple-600 font-medium">Rashi</p>
                <p className="text-sm text-gray-800 font-semibold mt-1">{person.rashi || '—'}</p>
              </div>
              <div className="bg-blue-50 rounded-lg p-3 text-center">
                <p className="text-xs text-blue-600 font-medium">Gotra</p>
                <p className="text-sm text-gray-800 font-semibold mt-1">{person.gotra || '—'}</p>
              </div>
              <div className="bg-green-50 rounded-lg p-3 text-center">
                <p className="text-xs text-green-600 font-medium">Kula</p>
                <p className="text-sm text-gray-800 font-semibold mt-1">{person.kula || '—'}</p>
              </div>
            </div>
            {person.pravara && (
              <div className="mt-3 bg-gray-50 rounded-lg p-3">
                <p className="text-xs text-gray-500 font-medium">Pravara (Sacred Lineage)</p>
                <p className="text-sm text-gray-700 mt-1">{person.pravara}</p>
              </div>
            )}
          </div>

          {/* Relationships */}
          <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
            <h3 className="font-semibold text-gray-800 mb-3 flex items-center gap-2">
              <Users size={18} className="text-green-600" />
              Family Relationships
            </h3>
            <div className="space-y-4">
              {/* Parents */}
              {(father || mother) && (
                <div>
                  <p className="text-xs text-gray-500 uppercase tracking-wider mb-2">Parents</p>
                  <div className="flex flex-wrap gap-2">
                    {father && (
                      <button
                        onClick={() => onSelectPerson(father)}
                        className="flex items-center gap-2 px-3 py-2 bg-blue-50 border border-blue-200 rounded-lg hover:shadow-sm transition-all"
                      >
                        <div className="w-6 h-6 bg-blue-500 rounded-full flex items-center justify-center text-white text-xs font-bold">
                          {father.firstName[0]}
                        </div>
                        <span className="text-sm text-gray-800">{father.firstName} {father.lastName}</span>
                        <span className="text-xs text-blue-600">Father</span>
                      </button>
                    )}
                    {mother && (
                      <button
                        onClick={() => onSelectPerson(mother)}
                        className="flex items-center gap-2 px-3 py-2 bg-pink-50 border border-pink-200 rounded-lg hover:shadow-sm transition-all"
                      >
                        <div className="w-6 h-6 bg-pink-500 rounded-full flex items-center justify-center text-white text-xs font-bold">
                          {mother.firstName[0]}
                        </div>
                        <span className="text-sm text-gray-800">{mother.firstName} {mother.lastName}</span>
                        <span className="text-xs text-pink-600">Mother</span>
                      </button>
                    )}
                  </div>
                </div>
              )}

              {/* Spouse */}
              {spouses.length > 0 && (
                <div>
                  <p className="text-xs text-gray-500 uppercase tracking-wider mb-2">Spouse</p>
                  <div className="flex flex-wrap gap-2">
                    {spouses.map(spouse => (
                      <button
                        key={spouse.id}
                        onClick={() => onSelectPerson(spouse)}
                        className="flex items-center gap-2 px-3 py-2 bg-red-50 border border-red-200 rounded-lg hover:shadow-sm transition-all"
                      >
                        <Heart size={14} className="text-red-400" />
                        <div className={`w-6 h-6 rounded-full flex items-center justify-center text-white text-xs font-bold ${
                          spouse.gender === 'male' ? 'bg-blue-500' : 'bg-pink-500'
                        }`}>
                          {spouse.firstName[0]}
                        </div>
                        <span className="text-sm text-gray-800">{spouse.firstName} {spouse.lastName}</span>
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* Children */}
              {children.length > 0 && (
                <div>
                  <p className="text-xs text-gray-500 uppercase tracking-wider mb-2">Children ({children.length})</p>
                  <div className="flex flex-wrap gap-2">
                    {children.map(child => (
                      <button
                        key={child.id}
                        onClick={() => onSelectPerson(child)}
                        className="flex items-center gap-2 px-3 py-2 bg-gray-50 border border-gray-200 rounded-lg hover:shadow-sm transition-all"
                      >
                        <div className={`w-6 h-6 rounded-full flex items-center justify-center text-white text-xs font-bold ${
                          child.gender === 'male' ? 'bg-blue-500' : 'bg-pink-500'
                        }`}>
                          {child.firstName[0]}
                        </div>
                        <span className="text-sm text-gray-800">{child.firstName} {child.lastName}</span>
                        <span className="text-xs text-gray-500">{child.birthDate?.split('-')[0]}</span>
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* Siblings */}
              {siblings.length > 0 && (
                <div>
                  <p className="text-xs text-gray-500 uppercase tracking-wider mb-2">Siblings ({siblings.length})</p>
                  <div className="flex flex-wrap gap-2">
                    {siblings.map(sibling => (
                      <button
                        key={sibling.id}
                        onClick={() => onSelectPerson(sibling)}
                        className="flex items-center gap-2 px-3 py-2 bg-purple-50 border border-purple-200 rounded-lg hover:shadow-sm transition-all"
                      >
                        <div className={`w-6 h-6 rounded-full flex items-center justify-center text-white text-xs font-bold ${
                          sibling.gender === 'male' ? 'bg-blue-500' : 'bg-pink-500'
                        }`}>
                          {sibling.firstName[0]}
                        </div>
                        <div className="text-left">
                          <span className="text-sm text-gray-800">{sibling.firstName} {sibling.lastName}</span>
                          <span className="text-[10px] text-purple-600 ml-1">
                            ({sibling.gender === 'male' ? 'Brother' : 'Sister'})
                          </span>
                        </div>
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* Grandparents */}
              {grandparents.length > 0 && (
                <div>
                  <p className="text-xs text-gray-500 uppercase tracking-wider mb-2">Grandparents ({grandparents.length})</p>
                  <div className="flex flex-wrap gap-2">
                    {grandparents.map(gp => {
                      const isPaternal = father && (father.fatherId === gp.id || father.motherId === gp.id);
                      const label = gp.gender === 'male' 
                        ? (isPaternal ? 'Paternal Grandfather (Dada)' : 'Maternal Grandfather (Nana)')
                        : (isPaternal ? 'Paternal Grandmother (Dadi)' : 'Maternal Grandmother (Nani)');
                      return (
                        <button
                          key={gp.id}
                          onClick={() => onSelectPerson(gp)}
                          className="flex items-center gap-2 px-3 py-2 bg-amber-50 border border-amber-200 rounded-lg hover:shadow-sm transition-all"
                        >
                          <div className={`w-6 h-6 rounded-full flex items-center justify-center text-white text-xs font-bold ${
                            gp.gender === 'male' ? 'bg-blue-500' : 'bg-pink-500'
                          }`}>
                            {gp.firstName[0]}
                          </div>
                          <div className="text-left">
                            <span className="text-sm text-gray-800">{gp.firstName} {gp.lastName}</span>
                            <span className="text-[10px] text-amber-600 block">{label}</span>
                          </div>
                        </button>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* Grandchildren */}
              {grandchildren.length > 0 && (
                <div>
                  <p className="text-xs text-gray-500 uppercase tracking-wider mb-2">Grandchildren ({grandchildren.length})</p>
                  <div className="flex flex-wrap gap-2">
                    {grandchildren.map(gc => (
                      <button
                        key={gc.id}
                        onClick={() => onSelectPerson(gc)}
                        className="flex items-center gap-2 px-3 py-2 bg-teal-50 border border-teal-200 rounded-lg hover:shadow-sm transition-all"
                      >
                        <div className={`w-6 h-6 rounded-full flex items-center justify-center text-white text-xs font-bold ${
                          gc.gender === 'male' ? 'bg-blue-500' : 'bg-pink-500'
                        }`}>
                          {gc.firstName[0]}
                        </div>
                        <div className="text-left">
                          <span className="text-sm text-gray-800">{gc.firstName} {gc.lastName}</span>
                          <span className="text-[10px] text-teal-600 block">
                            {gc.gender === 'male' ? 'Grandson (Pota/Dota)' : 'Granddaughter (Poti/Doti)'}
                          </span>
                        </div>
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* Uncles & Aunts */}
              {unclesAunts.length > 0 && (
                <div>
                  <p className="text-xs text-gray-500 uppercase tracking-wider mb-2">Uncles & Aunts ({unclesAunts.length})</p>
                  <div className="flex flex-wrap gap-2">
                    {unclesAunts.map(ua => {
                      const isPaternal = father && father.fatherId === ua.fatherId;
                      const label = ua.gender === 'male'
                        ? (isPaternal ? 'Paternal Uncle (Chacha/Tau)' : 'Maternal Uncle (Mama)')
                        : (isPaternal ? 'Paternal Aunt (Bua)' : 'Maternal Aunt (Mami)');
                      return (
                        <button
                          key={ua.id}
                          onClick={() => onSelectPerson(ua)}
                          className="flex items-center gap-2 px-3 py-2 bg-orange-50 border border-orange-200 rounded-lg hover:shadow-sm transition-all"
                        >
                          <div className={`w-6 h-6 rounded-full flex items-center justify-center text-white text-xs font-bold ${
                            ua.gender === 'male' ? 'bg-blue-500' : 'bg-pink-500'
                          }`}>
                            {ua.firstName[0]}
                          </div>
                          <div className="text-left">
                            <span className="text-sm text-gray-800">{ua.firstName} {ua.lastName}</span>
                            <span className="text-[10px] text-orange-600 block">{label}</span>
                          </div>
                        </button>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* Nephews & Nieces */}
              {nephewsNieces.length > 0 && (
                <div>
                  <p className="text-xs text-gray-500 uppercase tracking-wider mb-2">Nephews & Nieces ({nephewsNieces.length})</p>
                  <div className="flex flex-wrap gap-2">
                    {nephewsNieces.map(nn => (
                      <button
                        key={nn.id}
                        onClick={() => onSelectPerson(nn)}
                        className="flex items-center gap-2 px-3 py-2 bg-indigo-50 border border-indigo-200 rounded-lg hover:shadow-sm transition-all"
                      >
                        <div className={`w-6 h-6 rounded-full flex items-center justify-center text-white text-xs font-bold ${
                          nn.gender === 'male' ? 'bg-blue-500' : 'bg-pink-500'
                        }`}>
                          {nn.firstName[0]}
                        </div>
                        <div className="text-left">
                          <span className="text-sm text-gray-800">{nn.firstName} {nn.lastName}</span>
                          <span className="text-[10px] text-indigo-600 block">
                            {nn.gender === 'male' ? 'Nephew (Bhatija/Bhanja)' : 'Niece (Bhatiji/Bhanji)'}
                          </span>
                        </div>
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* Cousins */}
              {cousins.length > 0 && (
                <div>
                  <p className="text-xs text-gray-500 uppercase tracking-wider mb-2">Cousins ({cousins.length})</p>
                  <div className="flex flex-wrap gap-2">
                    {cousins.map(cousin => (
                      <button
                        key={cousin.id}
                        onClick={() => onSelectPerson(cousin)}
                        className="flex items-center gap-2 px-3 py-2 bg-pink-50 border border-pink-200 rounded-lg hover:shadow-sm transition-all"
                      >
                        <div className={`w-6 h-6 rounded-full flex items-center justify-center text-white text-xs font-bold ${
                          cousin.gender === 'male' ? 'bg-blue-500' : 'bg-pink-500'
                        }`}>
                          {cousin.firstName[0]}
                        </div>
                        <div className="text-left">
                          <span className="text-sm text-gray-800">{cousin.firstName} {cousin.lastName}</span>
                          <span className="text-[10px] text-pink-600 block">
                            {cousin.gender === 'male' ? 'Cousin Brother' : 'Cousin Sister'}
                          </span>
                        </div>
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* In-Laws */}
              {inLaws.length > 0 && (
                <div>
                  <p className="text-xs text-gray-500 uppercase tracking-wider mb-2">In-Laws ({inLaws.length})</p>
                  <div className="flex flex-wrap gap-2">
                    {inLaws.map((il, idx) => (
                      <button
                        key={`${il.person.id}-${idx}`}
                        onClick={() => onSelectPerson(il.person)}
                        className="flex items-center gap-2 px-3 py-2 bg-cyan-50 border border-cyan-200 rounded-lg hover:shadow-sm transition-all"
                      >
                        <div className={`w-6 h-6 rounded-full flex items-center justify-center text-white text-xs font-bold ${
                          il.person.gender === 'male' ? 'bg-blue-500' : 'bg-pink-500'
                        }`}>
                          {il.person.firstName[0]}
                        </div>
                        <div className="text-left">
                          <span className="text-sm text-gray-800">{il.person.firstName} {il.person.lastName}</span>
                          <span className="text-[10px] text-cyan-600 block">{il.label}</span>
                        </div>
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Right Column - Cultural Info */}
        <div className="space-y-6">
          {/* Kuladevata */}
          <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
            <h3 className="font-semibold text-gray-800 mb-3 flex items-center gap-2">
              <span className="text-lg">🛕</span>
              Kuladevata
            </h3>
            <div className="text-center py-4 bg-gradient-to-b from-amber-50 to-orange-50 rounded-lg">
              <p className="text-lg font-bold text-amber-800">{person.kuladevata || 'Not Recorded'}</p>
              {person.kuladevataTemple && (
                <p className="text-xs text-amber-600 mt-1 flex items-center justify-center gap-1">
                  <MapPin size={12} />
                  {person.kuladevataTemple}
                </p>
              )}
            </div>
          </div>

          {/* Ancestral Location */}
          <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
            <h3 className="font-semibold text-gray-800 mb-3 flex items-center gap-2">
              <MapPin size={18} className="text-green-600" />
              Ancestral Location
            </h3>
            <div className="space-y-2">
              {person.ancestralVillage && (
                <div className="flex items-center gap-2">
                  <span className="text-xs text-gray-500 w-16">Village:</span>
                  <span className="text-sm text-gray-800 font-medium">{person.ancestralVillage}</span>
                </div>
              )}
              {person.district && (
                <div className="flex items-center gap-2">
                  <span className="text-xs text-gray-500 w-16">District:</span>
                  <span className="text-sm text-gray-800">{person.district}</span>
                </div>
              )}
              {person.state && (
                <div className="flex items-center gap-2">
                  <span className="text-xs text-gray-500 w-16">State:</span>
                  <span className="text-sm text-gray-800">{person.state}</span>
                </div>
              )}
            </div>
          </div>

          {/* Privacy */}
          <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
            <h3 className="font-semibold text-gray-800 mb-3 flex items-center gap-2">
              <Shield size={18} className="text-red-600" />
              Privacy Status
            </h3>
            <div className={`p-3 rounded-lg ${person.isPrivate ? 'bg-red-50 border border-red-200' : 'bg-green-50 border border-green-200'}`}>
              <p className={`text-sm font-medium ${person.isPrivate ? 'text-red-700' : 'text-green-700'}`}>
                {person.isPrivate ? '🔒 Private - Hidden from non-family' : '🌐 Public - Visible to all'}
              </p>
              <p className="text-xs text-gray-500 mt-1">
                {person.isPrivate
                  ? 'This person\'s details are only visible to approved family members.'
                  : 'This person\'s details are visible to all family tree viewers.'}
              </p>
            </div>
          </div>

          {/* Notes */}
          {person.notes && (
            <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
              <h3 className="font-semibold text-gray-800 mb-3 flex items-center gap-2">
                <BookOpen size={18} className="text-gray-600" />
                Notes
              </h3>
              <p className="text-sm text-gray-700 leading-relaxed">{person.notes}</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

import { useState, useMemo } from 'react';
import { Person, ViewMode } from '../types';
import { sampleHouseholds } from '../data/sampleData';
import { LayoutGrid, GitBranch, List, ZoomIn, ZoomOut, Heart, Baby, Users } from 'lucide-react';

interface FamilyTreeProps {
  persons: Person[];
  rootPersonId: string;
  viewMode: ViewMode;
  onViewModeChange: (mode: ViewMode) => void;
  onSelectPerson: (person: Person) => void;
}

// Helper to determine relationship label
function getRelationshipLabel(person: Person, target: Person, persons: Person[]): string {
  // Spouse
  if (person.spouseIds.includes(target.id)) {
    return target.gender === 'male' ? 'Husband' : 'Wife';
  }
  // Parent
  if (person.fatherId === target.id) return 'Father';
  if (person.motherId === target.id) return 'Mother';
  // Children
  if (target.fatherId === person.id || target.motherId === person.id) {
    return target.gender === 'male' ? 'Son' : 'Daughter';
  }
  // Siblings
  if (person.fatherId && person.fatherId === target.fatherId && person.id !== target.id) {
    return target.gender === 'male' ? 'Brother' : 'Sister';
  }
  if (person.motherId && person.motherId === target.motherId && person.id !== target.id) {
    return target.gender === 'male' ? 'Brother' : 'Sister';
  }
  // Grandparent
  const personFather = persons.find(p => p.id === person.fatherId);
  const personMother = persons.find(p => p.id === person.motherId);
  if (personFather && (personFather.fatherId === target.id)) return 'Paternal Grandfather';
  if (personFather && (personFather.motherId === target.id)) return 'Paternal Grandmother';
  if (personMother && (personMother.fatherId === target.id)) return 'Maternal Grandfather';
  if (personMother && (personMother.motherId === target.id)) return 'Maternal Grandmother';
  // Grandchildren
  const children = persons.filter(p => p.fatherId === person.id || p.motherId === person.id);
  for (const child of children) {
    if (target.fatherId === child.id || target.motherId === child.id) {
      return target.gender === 'male' ? 'Grandson' : 'Granddaughter';
    }
  }
  // Uncle/Aunt (Father's siblings)
  if (personFather) {
    if (personFather.fatherId === target.fatherId && target.id !== personFather.id) {
      return target.gender === 'male' ? 'Paternal Uncle (Chacha/Tau)' : 'Paternal Aunt (Bua)';
    }
  }
  // Uncle/Aunt (Mother's siblings)
  if (personMother) {
    if (personMother.fatherId === target.fatherId && target.id !== personMother.id) {
      return target.gender === 'male' ? 'Maternal Uncle (Mama)' : 'Maternal Aunt (Mami)';
    }
  }
  // Nephew/Niece
  const siblings = persons.filter(p => {
    if (p.id === person.id) return false;
    return (person.fatherId && p.fatherId === person.fatherId) || (person.motherId && p.motherId === person.motherId);
  });
  for (const sibling of siblings) {
    if (target.fatherId === sibling.id || target.motherId === sibling.id) {
      return target.gender === 'male' ? 'Nephew (Bhatija/Bhanja)' : 'Niece (Bhatiji/Bhanji)';
    }
  }
  // Cousin
  const unclesAunts = persons.filter(p => {
    if (personFather && personFather.fatherId === p.fatherId && p.id !== personFather.id) return true;
    if (personMother && personMother.fatherId === p.fatherId && p.id !== personMother.id) return true;
    return false;
  });
  for (const ua of unclesAunts) {
    if (target.fatherId === ua.id || target.motherId === ua.id) {
      return target.gender === 'male' ? 'Cousin Brother' : 'Cousin Sister';
    }
  }
  // In-laws
  if (person.spouseIds.length > 0) {
    const spouse = persons.find(p => p.id === person.spouseIds[0]);
    if (spouse) {
      if (target.id === spouse.fatherId) return 'Father-in-law';
      if (target.id === spouse.motherId) return 'Mother-in-law';
      if (spouse.fatherId === target.fatherId && target.id !== spouse.id) {
        return target.gender === 'male' ? 'Brother-in-law (Devar/Devrani)' : 'Sister-in-law (Nanad)';
      }
      if (spouse.motherId === target.motherId && target.id !== spouse.id) {
        return target.gender === 'male' ? 'Brother-in-law (Saala)' : 'Sister-in-law (Saali)';
      }
      // Spouse's siblings' spouses
      const spouseSiblings = persons.filter(p => {
        if (p.id === spouse.id) return false;
        return (spouse.fatherId && p.fatherId === spouse.fatherId) || (spouse.motherId && p.motherId === spouse.motherId);
      });
      for (const ss of spouseSiblings) {
        if (ss.spouseIds.includes(target.id)) {
          return target.gender === 'male' ? 'Brother-in-law' : 'Sister-in-law';
        }
      }
    }
  }
  // Children's spouses
  for (const child of children) {
    if (child.spouseIds.includes(target.id)) {
      return target.gender === 'male' ? 'Son-in-law (Damad/Jawai)' : 'Daughter-in-law (Bahu)';
    }
  }
  return '';
}

// Relationship color mapping
function getRelationshipColor(label: string): string {
  if (label.includes('Husband') || label.includes('Wife')) return 'bg-red-100 text-red-700 border-red-200';
  if (label.includes('Father') || label.includes('Mother')) return 'bg-blue-100 text-blue-700 border-blue-200';
  if (label.includes('Son') || label.includes('Daughter')) return 'bg-green-100 text-green-700 border-green-200';
  if (label.includes('Brother') || label.includes('Sister')) return 'bg-purple-100 text-purple-700 border-purple-200';
  if (label.includes('Grandfather') || label.includes('Grandmother')) return 'bg-amber-100 text-amber-700 border-amber-200';
  if (label.includes('Grandson') || label.includes('Granddaughter')) return 'bg-teal-100 text-teal-700 border-teal-200';
  if (label.includes('Uncle') || label.includes('Aunt')) return 'bg-orange-100 text-orange-700 border-orange-200';
  if (label.includes('Nephew') || label.includes('Niece')) return 'bg-indigo-100 text-indigo-700 border-indigo-200';
  if (label.includes('Cousin')) return 'bg-pink-100 text-pink-700 border-pink-200';
  if (label.includes('in-law')) return 'bg-cyan-100 text-cyan-700 border-cyan-200';
  return 'bg-gray-100 text-gray-700 border-gray-200';
}

export default function FamilyTree({ persons, rootPersonId, viewMode, onViewModeChange, onSelectPerson }: FamilyTreeProps) {
  const [zoom, setZoom] = useState(1);
  const [focusedPerson, setFocusedPerson] = useState<string>(rootPersonId);
  const rootPerson = persons.find(p => p.id === rootPersonId);

  const focusedPersonObj = persons.find(p => p.id === focusedPerson);

  // Get all relationships for focused person
  const relationships = useMemo(() => {
    if (!focusedPersonObj) return [];
    return persons
      .filter(p => p.id !== focusedPerson)
      .map(p => ({
        person: p,
        label: getRelationshipLabel(focusedPersonObj!, p, persons)
      }))
      .filter(r => r.label !== '')
      .sort((a, b) => {
        const order = ['Husband', 'Wife', 'Father', 'Mother', 'Son', 'Daughter', 'Brother', 'Sister', 'Paternal Grandfather', 'Paternal Grandmother', 'Maternal Grandfather', 'Maternal Grandmother'];
        const aIdx = order.findIndex(o => a.label.includes(o));
        const bIdx = order.findIndex(o => b.label.includes(o));
        if (aIdx === -1 && bIdx === -1) return a.label.localeCompare(b.label);
        if (aIdx === -1) return 1;
        if (bIdx === -1) return -1;
        return aIdx - bIdx;
      });
  }, [focusedPersonObj, persons]);

  return (
    <div className="h-full flex flex-col">
      {/* Toolbar */}
      <div className="bg-white border-b border-gray-200 px-6 py-3 flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-2">
          <h2 className="text-lg font-semibold text-gray-800">Family Tree</h2>
          <span className="text-sm text-gray-500">— {rootPerson?.firstName} {rootPerson?.lastName}'s Lineage</span>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          {/* View Mode Toggle */}
          <div className="flex bg-gray-100 rounded-lg p-1">
            <button
              onClick={() => onViewModeChange('cluster')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
                viewMode === 'cluster' ? 'bg-white shadow text-amber-700' : 'text-gray-600 hover:text-gray-800'
              }`}
            >
              <LayoutGrid size={14} /> Cluster
            </button>
            <button
              onClick={() => onViewModeChange('tree')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
                viewMode === 'tree' ? 'bg-white shadow text-amber-700' : 'text-gray-600 hover:text-gray-800'
              }`}
            >
              <GitBranch size={14} /> Pedigree
            </button>
            <button
              onClick={() => onViewModeChange('list')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
                viewMode === 'list' ? 'bg-white shadow text-amber-700' : 'text-gray-600 hover:text-gray-800'
              }`}
            >
              <List size={14} /> List
            </button>
            <button
              onClick={() => onViewModeChange('relations')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
                viewMode === 'relations' ? 'bg-white shadow text-amber-700' : 'text-gray-600 hover:text-gray-800'
              }`}
            >
              <Users size={14} /> Relations
            </button>
          </div>

          {/* Zoom Controls */}
          <div className="flex items-center gap-1 ml-2">
            <button
              onClick={() => setZoom(Math.max(0.5, zoom - 0.1))}
              className="p-1.5 rounded-md hover:bg-gray-100 text-gray-600"
            >
              <ZoomOut size={16} />
            </button>
            <span className="text-xs text-gray-500 w-10 text-center">{Math.round(zoom * 100)}%</span>
            <button
              onClick={() => setZoom(Math.min(2, zoom + 0.1))}
              className="p-1.5 rounded-md hover:bg-gray-100 text-gray-600"
            >
              <ZoomIn size={16} />
            </button>
          </div>
        </div>
      </div>

      {/* Tree Content */}
      <div className="flex-1 overflow-auto p-6 bg-gray-50">
        {viewMode === 'cluster' && (
          <ClusterView persons={persons} onSelectPerson={onSelectPerson} zoom={zoom} />
        )}
        {viewMode === 'tree' && (
          <PedigreeView persons={persons} rootPersonId={rootPersonId} onSelectPerson={onSelectPerson} zoom={zoom} />
        )}
        {viewMode === 'list' && (
          <ListView persons={persons} onSelectPerson={onSelectPerson} />
        )}
        {viewMode === 'relations' && (
          <RelationsView
            persons={persons}
            focusedPerson={focusedPerson}
            onFocusPerson={setFocusedPerson}
            relationships={relationships}
            onSelectPerson={onSelectPerson}
          />
        )}
      </div>
    </div>
  );
}

// ===================== RELATIONS VIEW =====================
function RelationsView({ persons, focusedPerson, onFocusPerson, relationships, onSelectPerson }: {
  persons: Person[];
  focusedPerson: string;
  onFocusPerson: (id: string) => void;
  relationships: { person: Person; label: string }[];
  onSelectPerson: (p: Person) => void;
}) {
  const focused = persons.find(p => p.id === focusedPerson);

  // Group relationships by type
  const grouped = relationships.reduce((acc, rel) => {
    let category = 'Other';
    if (rel.label.includes('Husband') || rel.label.includes('Wife')) category = 'Spouse';
    else if (rel.label.includes('Father') && !rel.label.includes('in-law') && !rel.label.includes('Grandfather')) category = 'Parents';
    else if (rel.label.includes('Mother') && !rel.label.includes('in-law') && !rel.label.includes('Grandmother')) category = 'Parents';
    else if (rel.label.includes('Son') && !rel.label.includes('in-law') && !rel.label.includes('Grandson')) category = 'Children';
    else if (rel.label.includes('Daughter') && !rel.label.includes('in-law') && !rel.label.includes('Granddaughter')) category = 'Children';
    else if (rel.label.includes('Brother') && !rel.label.includes('in-law') && !rel.label.includes('Cousin')) category = 'Siblings';
    else if (rel.label.includes('Sister') && !rel.label.includes('in-law') && !rel.label.includes('Cousin')) category = 'Siblings';
    else if (rel.label.includes('Grandfather') || rel.label.includes('Grandmother')) category = 'Grandparents';
    else if (rel.label.includes('Grandson') || rel.label.includes('Granddaughter')) category = 'Grandchildren';
    else if (rel.label.includes('Uncle') || rel.label.includes('Aunt')) category = 'Uncles & Aunts';
    else if (rel.label.includes('Nephew') || rel.label.includes('Niece')) category = 'Nephews & Nieces';
    else if (rel.label.includes('Cousin')) category = 'Cousins';
    else if (rel.label.includes('in-law')) category = 'In-Laws';
    
    if (!acc[category]) acc[category] = [];
    acc[category].push(rel);
    return acc;
  }, {} as Record<string, { person: Person; label: string }[]>);

  const categoryOrder = ['Spouse', 'Parents', 'Children', 'Siblings', 'Grandparents', 'Grandchildren', 'Uncles & Aunts', 'Nephews & Nieces', 'Cousins', 'In-Laws', 'Other'];

  return (
    <div className="max-w-6xl mx-auto">
      {/* Focus Person Selector */}
      <div className="bg-white rounded-xl border border-gray-200 p-4 mb-6 shadow-sm">
        <label className="block text-sm font-medium text-gray-700 mb-2">
          👤 View relationships for:
        </label>
        <select
          value={focusedPerson}
          onChange={(e) => onFocusPerson(e.target.value)}
          className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-amber-500"
        >
          {persons.map(p => (
            <option key={p.id} value={p.id}>
              {p.firstName} {p.lastName} {p.isLiving ? '' : '(✝)'}
            </option>
          ))}
        </select>
      </div>

      {focused && (
        <>
          {/* Focused Person Card */}
          <div className="bg-gradient-to-r from-amber-700 to-orange-700 rounded-xl p-5 mb-6 text-white shadow-lg">
            <div className="flex items-center gap-4">
              <div className={`w-16 h-16 rounded-full flex items-center justify-center text-2xl font-bold border-3 border-white/50 ${
                focused.gender === 'male' ? 'bg-blue-500' : 'bg-pink-500'
              }`}>
                {focused.firstName[0]}
              </div>
              <div>
                <h3 className="text-xl font-bold">{focused.firstName} {focused.lastName}</h3>
                <p className="text-amber-200 text-sm">
                  {focused.gotra} Gotra • {focused.ancestralVillage || 'Unknown village'}
                </p>
                <p className="text-amber-100 text-xs mt-1">
                  {relationships.length} relationships found in family tree
                </p>
              </div>
            </div>
          </div>

          {/* Relationship Groups */}
          <div className="space-y-4">
            {categoryOrder.map(category => {
              const rels = grouped[category];
              if (!rels || rels.length === 0) return null;
              return (
                <div key={category} className="bg-white rounded-xl border border-gray-200 overflow-hidden shadow-sm">
                  <div className="bg-gray-50 px-4 py-3 border-b border-gray-200 flex items-center gap-2">
                    <span className="text-sm">
                      {category === 'Spouse' && '💑'}
                      {category === 'Parents' && '👨‍👩‍👦'}
                      {category === 'Children' && '👶'}
                      {category === 'Siblings' && '👫'}
                      {category === 'Grandparents' && '👴'}
                      {category === 'Grandchildren' && '🧒'}
                      {category === 'Uncles & Aunts' && '🧑‍🦳'}
                      {category === 'Nephews & Nieces' && '👦'}
                      {category === 'Cousins' && '👨‍👩‍👧‍👦'}
                      {category === 'In-Laws' && '🤝'}
                      {category === 'Other' && '👤'}
                    </span>
                    <h4 className="font-semibold text-gray-800 text-sm">{category}</h4>
                    <span className="text-xs bg-gray-200 text-gray-600 px-2 py-0.5 rounded-full">{rels.length}</span>
                  </div>
                  <div className="p-4">
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                      {rels.map(rel => (
                        <button
                          key={rel.person.id}
                          onClick={() => onSelectPerson(rel.person)}
                          className="flex items-center gap-3 p-3 rounded-lg border border-gray-200 hover:border-amber-300 hover:bg-amber-50 transition-all text-left group"
                        >
                          <div className={`w-10 h-10 rounded-full flex items-center justify-center text-white font-bold text-sm flex-shrink-0 ${
                            rel.person.gender === 'male' ? 'bg-blue-500' : 'bg-pink-500'
                          }`}>
                            {rel.person.firstName[0]}
                          </div>
                          <div className="flex-1 min-w-0">
                            <p className="text-sm font-medium text-gray-800 truncate group-hover:text-amber-800">
                              {rel.person.firstName} {rel.person.lastName}
                            </p>
                            <span className={`inline-block text-[10px] px-2 py-0.5 rounded-full border mt-0.5 ${getRelationshipColor(rel.label)}`}>
                              {rel.label}
                            </span>
                          </div>
                          <span className={`w-2 h-2 rounded-full flex-shrink-0 ${rel.person.isLiving ? 'bg-green-400' : 'bg-gray-400'}`} />
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
              );
            })}

            {relationships.length === 0 && (
              <div className="text-center py-12 bg-white rounded-xl border border-gray-200">
                <p className="text-gray-500">No relationships found for this person in the tree.</p>
                <p className="text-xs text-gray-400 mt-1">Add family connections to see relationships.</p>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}

// ===================== CLUSTER VIEW =====================
function ClusterView({ persons, onSelectPerson, zoom }: { persons: Person[]; onSelectPerson: (p: Person) => void; zoom: number }) {
  return (
    <div className="space-y-8" style={{ transform: `scale(${zoom})`, transformOrigin: 'top left' }}>
      {/* Root Generation */}
      <div className="text-center mb-4">
        <span className="text-xs font-medium text-gray-500 uppercase tracking-wider">Root Generation (1920s)</span>
      </div>
      <div className="flex justify-center mb-8">
        {persons.filter(p => !p.fatherId && !p.motherId && p.spouseIds.length > 0 && !p.isLiving).map(person => {
          const spouse = persons.find(p => p.id === person.spouseIds[0]);
          return (
            <div key={person.id} className="flex items-center gap-1">
              <PersonNode person={person} onClick={() => onSelectPerson(person)} isRoot />
              {spouse && (
                <>
                  <div className="flex flex-col items-center mx-1">
                    <Heart size={14} className="text-red-400" />
                    <span className="text-[9px] text-red-400">married</span>
                  </div>
                  <PersonNode person={spouse} onClick={() => onSelectPerson(spouse)} isRoot />
                </>
              )}
            </div>
          );
        })}
      </div>

      {/* Generation 2 - Children of Root */}
      <div className="text-center mb-4">
        <span className="text-xs font-medium text-gray-500 uppercase tracking-wider">Generation 2 (Children)</span>
      </div>
      <div className="flex justify-center flex-wrap gap-6 mb-8">
        {persons.filter(p => {
          const root = persons.find(r => r.id === 'p1');
          return root && root.childrenIds.includes(p.id);
        }).map(child => {
          const spouse = child.spouseIds.length > 0 ? persons.find(p => p.id === child.spouseIds[0]) : null;
          return (
            <div key={child.id} className="flex flex-col items-center">
              <div className="flex items-center gap-1">
                <PersonNode person={child} onClick={() => onSelectPerson(child)} />
                {spouse && (
                  <>
                    <div className="flex flex-col items-center mx-1">
                      <Heart size={12} className="text-red-400" />
                      <span className="text-[9px] text-red-400">spouse</span>
                    </div>
                    <PersonNode person={spouse} onClick={() => onSelectPerson(spouse)} />
                  </>
                )}
              </div>
              <span className="text-[10px] text-amber-700 mt-1 bg-amber-50 px-2 py-0.5 rounded-full">Son/Daughter of Root</span>
            </div>
          );
        })}
      </div>

      {/* Households */}
      <div className="text-center mb-4">
        <span className="text-xs font-medium text-gray-500 uppercase tracking-wider">Households / Joint Family Clusters</span>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
        {sampleHouseholds.map(household => {
          const members = household.memberIds.map(id => persons.find(p => p.id === id)).filter(Boolean) as Person[];
          
          return (
            <div key={household.id} className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
              <div className="bg-gradient-to-r from-amber-50 to-orange-50 px-4 py-3 border-b border-amber-100">
                <h4 className="font-medium text-gray-800 text-sm">{household.name}</h4>
                <p className="text-xs text-gray-500">{household.location}</p>
              </div>
              <div className="p-4">
                <div className="space-y-2">
                  {members.map(member => {
                    // Determine role in household
                    let role = 'Member';
                    if (member.id === household.headId) role = '👑 Head of Household';
                    else if (member.fatherId && members.some(m => m.id === member.fatherId)) role = '👦 Son/Daughter';
                    else if (member.motherId && members.some(m => m.id === member.motherId)) role = '👦 Son/Daughter';
                    else if (member.spouseIds.some(id => members.some(m => m.id === id))) role = '💑 Spouse';
                    
                    return (
                      <button
                        key={member.id}
                        onClick={() => onSelectPerson(member)}
                        className={`w-full flex items-center gap-3 p-2.5 rounded-lg border transition-all hover:shadow-md text-left ${
                          member.id === household.headId
                            ? 'border-amber-300 bg-amber-50'
                            : 'border-gray-200 hover:border-amber-200'
                        }`}
                      >
                        <div className={`w-8 h-8 rounded-full flex items-center justify-center text-white text-xs font-bold flex-shrink-0 ${
                          member.gender === 'male' ? 'bg-blue-500' : 'bg-pink-500'
                        }`}>
                          {member.firstName[0]}
                        </div>
                        <div className="flex-1 min-w-0">
                          <p className="text-xs font-medium text-gray-800 truncate">{member.firstName} {member.lastName}</p>
                          <p className="text-[10px] text-gray-500">{role}</p>
                        </div>
                        <span className={`w-2 h-2 rounded-full flex-shrink-0 ${member.isLiving ? 'bg-green-400' : 'bg-gray-400'}`} />
                      </button>
                    );
                  })}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Legend */}
      <div className="bg-white rounded-xl p-4 border border-gray-200">
        <h4 className="text-sm font-medium text-gray-700 mb-3">Legend</h4>
        <div className="flex flex-wrap gap-4 text-xs">
          <span className="flex items-center gap-2"><span className="w-3 h-3 rounded-full bg-blue-500"></span> Male</span>
          <span className="flex items-center gap-2"><span className="w-3 h-3 rounded-full bg-pink-500"></span> Female</span>
          <span className="flex items-center gap-2"><span className="w-3 h-3 rounded-full bg-green-400"></span> Living</span>
          <span className="flex items-center gap-2"><span className="w-3 h-3 rounded-full bg-gray-400"></span> Deceased</span>
          <span className="flex items-center gap-2"><Heart size={12} className="text-red-400" /> Marriage</span>
          <span className="flex items-center gap-2"><span className="w-4 h-4 rounded border-2 border-amber-300 bg-amber-50"></span> Household Head</span>
        </div>
      </div>
    </div>
  );
}

// ===================== PEDIGREE VIEW =====================
function PedigreeView({ persons, rootPersonId, onSelectPerson, zoom }: { persons: Person[]; rootPersonId: string; onSelectPerson: (p: Person) => void; zoom: number }) {
  const root = persons.find(p => p.id === rootPersonId);
  if (!root) return null;

  const getChildren = (personId: string) => persons.filter(p => p.fatherId === personId || p.motherId === personId);
  const getSpouse = (person: Person) => person.spouseIds.map(id => persons.find(p => p.id === id)).filter(Boolean) as Person[];

  const renderGeneration = (person: Person, depth: number = 0): React.ReactNode => {
    const children = getChildren(person.id).filter(c => {
      // Avoid duplicates - only show children once (via father if available)
      if (c.motherId && c.fatherId && c.fatherId !== person.id) return false;
      return true;
    });
    const spouses = getSpouse(person);

    return (
      <div key={person.id} className="flex flex-col items-center">
        {/* Person + Spouse */}
        <div className="flex items-center gap-1 mb-1">
          <button
            onClick={() => onSelectPerson(person)}
            className={`px-3 py-2 rounded-lg border-2 transition-all hover:shadow-lg ${
              person.gender === 'male' ? 'border-blue-300 bg-blue-50' : 'border-pink-300 bg-pink-50'
            }`}
          >
            <p className="text-xs font-medium text-gray-800">{person.firstName} {person.lastName}</p>
            <p className="text-[10px] text-gray-500">
              {person.birthDate?.split('-')[0]}{person.deathDate ? ` - ${person.deathDate.split('-')[0]}` : ' - present'}
            </p>
          </button>
          {spouses.map(s => (
            <div key={s.id} className="flex items-center">
              <div className="flex flex-col items-center mx-0.5">
                <Heart size={10} className="text-red-400" />
                <span className="text-[8px] text-red-400">wife</span>
              </div>
              <button
                onClick={() => onSelectPerson(s)}
                className={`px-3 py-2 rounded-lg border-2 transition-all hover:shadow-lg ${
                  s.gender === 'male' ? 'border-blue-300 bg-blue-50' : 'border-pink-300 bg-pink-50'
                }`}
              >
                <p className="text-xs font-medium text-gray-800">{s.firstName} {s.lastName}</p>
                <p className="text-[10px] text-gray-500">
                  {s.birthDate?.split('-')[0]}{s.deathDate ? ` - ${s.deathDate.split('-')[0]}` : ' - present'}
                </p>
              </button>
            </div>
          ))}
        </div>

        {/* Children with relationship labels */}
        {children.length > 0 && (
          <div className="flex flex-col items-center">
            <div className="w-px h-4 bg-gray-300"></div>
            <div className="flex gap-3 relative">
              {/* Horizontal line connecting children */}
              {children.length > 1 && (
                <div className="absolute top-0 left-1/2 -translate-x-1/2 h-px bg-gray-300" style={{ width: `${(children.length - 1) * 100}%` }}></div>
              )}
              {children.map((child, idx) => (
                <div key={child.id} className="flex flex-col items-center">
                  <div className="w-px h-4 bg-gray-300"></div>
                  <span className="text-[9px] text-gray-500 bg-gray-100 px-1.5 py-0.5 rounded mb-1">
                    {child.gender === 'male' ? '👦 Son' : '👧 Daughter'}
                  </span>
                  {renderGeneration(child, depth + 1)}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="overflow-x-auto" style={{ transform: `scale(${zoom})`, transformOrigin: 'top left' }}>
      <div className="min-w-max p-8">
        <div className="flex justify-center">
          {renderGeneration(root)}
        </div>
      </div>
    </div>
  );
}

// ===================== LIST VIEW =====================
function ListView({ persons, onSelectPerson }: { persons: Person[]; onSelectPerson: (p: Person) => void }) {
  const generations = [
    { label: 'Generation 1 (Grandparents)', filter: (p: Person) => !p.fatherId && !p.motherId && p.childrenIds.length > 0 },
    { label: 'Generation 2 (Parents)', filter: (p: Person) => {
      const parent = persons.find(pp => pp.childrenIds.includes(p.id));
      return parent && !parent.fatherId;
    }},
    { label: 'Generation 3 (Current)', filter: (p: Person) => {
      const parent = persons.find(pp => pp.childrenIds.includes(p.id));
      if (!parent) return false;
      const grandparent = persons.find(pp => pp.childrenIds.includes(parent.id));
      return grandparent && !grandparent.fatherId;
    }},
    { label: 'Generation 4 (Children)', filter: (p: Person) => {
      const parent = persons.find(pp => pp.childrenIds.includes(p.id));
      if (!parent) return false;
      const grandparent = persons.find(pp => pp.childrenIds.includes(parent.id));
      if (!grandparent) return false;
      const greatGrandparent = persons.find(pp => pp.childrenIds.includes(grandparent.id));
      return !!greatGrandparent;
    }},
  ];

  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      {generations.map((gen, idx) => {
        const members = persons.filter(gen.filter);
        if (members.length === 0) return null;
        return (
          <div key={idx} className="bg-white rounded-xl border border-gray-200 overflow-hidden">
            <div className="bg-gray-50 px-4 py-3 border-b border-gray-200">
              <h4 className="font-medium text-gray-700 text-sm">{gen.label}</h4>
            </div>
            <div className="divide-y divide-gray-100">
              {members.map(person => {
                // Find spouse
                const spouse = person.spouseIds.length > 0 ? persons.find(p => p.id === person.spouseIds[0]) : null;
                return (
                  <div key={person.id} className="px-4 py-3">
                    <button
                      onClick={() => onSelectPerson(person)}
                      className="flex items-center gap-4 hover:bg-amber-50 rounded-lg p-2 -m-2 transition-colors w-full text-left"
                    >
                      <div className={`w-10 h-10 rounded-full flex items-center justify-center text-white font-bold ${
                        person.gender === 'male' ? 'bg-blue-500' : 'bg-pink-500'
                      }`}>
                        {person.firstName[0]}
                      </div>
                      <div className="flex-1">
                        <p className="text-sm font-medium text-gray-800">{person.firstName} {person.lastName}</p>
                        <p className="text-xs text-gray-500">{person.gotra} • {person.occupation}</p>
                      </div>
                      <div className="text-right">
                        <p className="text-xs text-gray-500">{person.ancestralVillage}</p>
                        <span className={`text-[10px] px-2 py-0.5 rounded-full ${
                          person.isLiving ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-600'
                        }`}>
                          {person.isLiving ? 'Living' : 'Deceased'}
                        </span>
                      </div>
                    </button>
                    {spouse && (
                      <div className="ml-14 mt-1 flex items-center gap-2">
                        <Heart size={10} className="text-red-400" />
                        <button
                          onClick={() => onSelectPerson(spouse)}
                          className="text-xs text-gray-600 hover:text-amber-700 flex items-center gap-1"
                        >
                          <span className={`w-5 h-5 rounded-full flex items-center justify-center text-white text-[10px] font-bold ${
                            spouse.gender === 'male' ? 'bg-blue-400' : 'bg-pink-400'
                          }`}>
                            {spouse.firstName[0]}
                          </span>
                          {spouse.firstName} {spouse.lastName}
                          <span className="text-gray-400">({spouse.gender === 'male' ? 'Husband' : 'Wife'})</span>
                        </button>
                      </div>
                    )}
                    {/* Show children inline */}
                    {person.childrenIds.length > 0 && (
                      <div className="ml-14 mt-2 flex flex-wrap gap-1">
                        <span className="text-[10px] text-gray-400">Children:</span>
                        {person.childrenIds.map(childId => {
                          const child = persons.find(p => p.id === childId);
                          if (!child) return null;
                          return (
                            <button
                              key={childId}
                              onClick={() => onSelectPerson(child)}
                              className="text-[10px] bg-gray-100 text-gray-600 px-1.5 py-0.5 rounded hover:bg-amber-100 hover:text-amber-800"
                            >
                              {child.gender === 'male' ? '👦' : '👧'} {child.firstName}
                            </button>
                          );
                        })}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ===================== PERSON NODE =====================
function PersonNode({ person, onClick, isRoot }: { person: Person; onClick: () => void; isRoot?: boolean }) {
  return (
    <button
      onClick={onClick}
      className={`flex flex-col items-center p-3 rounded-xl border-2 transition-all hover:shadow-lg ${
        isRoot ? 'border-amber-400 bg-amber-50 shadow-md' : 'border-gray-200 bg-white'
      }`}
    >
      <div className={`w-10 h-10 rounded-full flex items-center justify-center text-white font-bold mb-1.5 ${
        person.gender === 'male' ? 'bg-blue-500' : 'bg-pink-500'
      }`}>
        {person.firstName[0]}
      </div>
      <p className="text-xs font-medium text-gray-800">{person.firstName} {person.lastName}</p>
      <p className="text-[10px] text-gray-500">{person.birthDate?.split('-')[0]} - {person.deathDate?.split('-')[0] || 'present'}</p>
      {person.gotra && (
        <span className="mt-1 text-[9px] bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded-full">
          {person.gotra}
        </span>
      )}
    </button>
  );
}

import { Page } from '../types';
import {
  Home,
  GitBranch,
  Users,
  UserPlus,
  Search,
  MapPin,
  Settings,
  ChevronLeft,
  ChevronRight,
  TreePine
} from 'lucide-react';

interface SidebarProps {
  currentPage: Page;
  onNavigate: (page: Page) => void;
  isOpen: boolean;
  onToggle: () => void;
}

const navItems: { page: Page; label: string; icon: React.ReactNode; labelHindi?: string }[] = [
  { page: 'dashboard', label: 'Dashboard', icon: <Home size={20} />, labelHindi: 'डैशबोर्ड' },
  { page: 'tree', label: 'Family Tree', icon: <GitBranch size={20} />, labelHindi: 'वंश वृक्ष' },
  { page: 'members', label: 'Members', icon: <Users size={20} />, labelHindi: 'सदस्य' },
  { page: 'add', label: 'Add Member', icon: <UserPlus size={20} />, labelHindi: 'सदस्य जोड़ें' },
  { page: 'search', label: 'Search', icon: <Search size={20} />, labelHindi: 'खोजें' },
  { page: 'gotra', label: 'Gotra & Kuladevata', icon: <MapPin size={20} />, labelHindi: 'गोत्र और कुलदेवता' },
];

export default function Sidebar({ currentPage, onNavigate, isOpen, onToggle }: SidebarProps) {
  return (
    <aside
      className={`${
        isOpen ? 'w-64' : 'w-16'
      } bg-gradient-to-b from-amber-900 via-amber-800 to-amber-900 text-white flex flex-col transition-all duration-300 relative shadow-2xl`}
    >
      {/* Header */}
      <div className="p-4 border-b border-amber-700/50">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-amber-600 rounded-lg flex items-center justify-center shadow-lg">
            <TreePine size={22} className="text-amber-100" />
          </div>
          {isOpen && (
            <div>
              <h1 className="text-lg font-bold text-amber-100">Vanshavali</h1>
              <p className="text-xs text-amber-300">वंशावली • Indian Family Tree</p>
            </div>
          )}
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 py-4 space-y-1 px-2">
        {navItems.map((item) => (
          <button
            key={item.page}
            onClick={() => onNavigate(item.page)}
            className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all duration-200 ${
              currentPage === item.page
                ? 'bg-amber-600/60 text-amber-50 shadow-md'
                : 'text-amber-200 hover:bg-amber-700/40 hover:text-white'
            }`}
          >
            <span className="flex-shrink-0">{item.icon}</span>
            {isOpen && (
              <div className="text-left">
                <span className="text-sm font-medium">{item.label}</span>
                {item.labelHindi && (
                  <span className="block text-xs text-amber-400/70">{item.labelHindi}</span>
                )}
              </div>
            )}
          </button>
        ))}
      </nav>

      {/* Footer */}
      <div className="p-2 border-t border-amber-700/50">
        <button className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-amber-200 hover:bg-amber-700/40 hover:text-white transition-all">
          <Settings size={20} />
          {isOpen && <span className="text-sm">Settings</span>}
        </button>
      </div>

      {/* Toggle Button */}
      <button
        onClick={onToggle}
        className="absolute -right-3 top-20 w-6 h-6 bg-amber-700 rounded-full flex items-center justify-center shadow-lg hover:bg-amber-600 transition-colors border-2 border-amber-500"
      >
        {isOpen ? <ChevronLeft size={12} /> : <ChevronRight size={12} />}
      </button>
    </aside>
  );
}


import {
  Zap,
  LayoutDashboard,
  MapPin,
  BatteryCharging,
  Wallet,
  ArrowLeftRight,
  Activity,
} from 'lucide-react'
import { NavLink } from 'react-router-dom'

const menu = [
  { name: 'Dashboard', path: '/', icon: LayoutDashboard },
  { name: 'Estaciones', path: '/estaciones', icon: MapPin },
  { name: 'Sesiones de carga', path: '/sesiones', icon: BatteryCharging },
  { name: 'Billetera digital', path: '/billetera', icon: Wallet },
  { name: 'Transacciones SAGA', path: '/transacciones', icon: ArrowLeftRight },
  { name: 'Observabilidad', path: '/observabilidad', icon: Activity },
]

export default function Sidebar() {
  return (
    <aside className="fixed left-0 top-0 flex h-screen w-64 flex-col border-r border-[#263449] bg-[#111b2d]">

      <div className="flex items-center gap-3 px-6 py-8">
        <div className="rounded-xl bg-emerald-400/10 p-2">
          <Zap className="text-emerald-400" size={28} />
        </div>
        <div>
          <h1 className="text-xl font-bold text-white">
            Aegis<span className="text-emerald-400">Volt</span>
          </h1>
          <p className="text-xs text-slate-400">
            EV Charging Platform
          </p>
        </div>
      </div>

      <p className="px-6 pb-3 text-xs font-semibold tracking-widest text-slate-500">
        PLATAFORMA
      </p>

      <nav className="flex flex-col gap-2 px-3">
        {menu.map(({ name, path, icon: Icon }) => (
          <NavLink
            key={path}
            to={path}
            end={path === '/'}
            className={({ isActive }) =>
              `flex items-center gap-3 rounded-lg px-4 py-3 text-sm transition-colors ${
                isActive
                  ? 'bg-emerald-400/10 text-emerald-400'
                  : 'text-slate-400 hover:bg-slate-800 hover:text-white'
              }`
            }
          >
            <Icon size={19} />
            {name}
          </NavLink>
        ))}
      </nav>

      <div className="mt-auto border-t border-[#263449] p-6">
        <div className="flex items-center gap-2">
          <span className="h-2 w-2 rounded-full bg-emerald-400" />
          <span className="text-sm text-slate-400">
            Entorno local
          </span>
        </div>
        <p className="mt-2 text-xs text-slate-500">
          AegisVolt v1.0
        </p>
      </div>
    </aside>
  )
}

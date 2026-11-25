
import {
  PlugZap,
  BatteryCharging,
  Wallet,
  ArrowLeftRight,
  Plus,
} from 'lucide-react'

import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Legend,
} from 'recharts'

import { Link } from 'react-router-dom'
import StatCard from '../components/StatCard'

const activityData = [
  { hour: '08:00', energy: 12 },
  { hour: '10:00', energy: 28 },
  { hour: '12:00', energy: 20 },
  { hour: '14:00', energy: 45 },
  { hour: '16:00', energy: 35 },
  { hour: '18:00', energy: 52 },
  { hour: '20:00', energy: 65 },
]

const connectorData = [
  { name: 'Disponibles', value: 8, color: '#34d399' },
  { name: 'Ocupados', value: 4, color: '#3b82f6' },
]

const transactions = [
  {
    id: 'SAGA-001',
    connector: 'connector-1',
    status: 'SUCCEEDED',
    amount: 12,
  },
  {
    id: 'SAGA-002',
    connector: 'connector-2',
    status: 'COMPENSATED',
    amount: 12,
  },
]

export default function Dashboard() {
  return (
    <div className="space-y-7">

      {/* Encabezado */}
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold">
            Dashboard
          </h1>
          <p className="mt-2 text-sm text-slate-400">
            Centro de control de infraestructura eléctrica
          </p>
        </div>

        <Link
          to="/sesiones"
          className="flex items-center gap-2 rounded-lg bg-emerald-400 px-5 py-3 text-sm font-semibold text-slate-950 transition hover:bg-emerald-300"
        >
          <Plus size={19} />
          Nueva carga
        </Link>
      </header>

      <div className="rounded-lg border border-amber-400/20 bg-amber-400/5 px-4 py-3 text-xs text-amber-300">
        Modo demostración — datos de ejemplo
      </div>

      {/* Indicadores */}
      <section className="grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-4">

        <StatCard
          title="Conectores"
          value="12"
          description="8 conectores disponibles"
          icon={PlugZap}
          color="#34d399"
        />

        <StatCard
          title="Sesiones activas"
          value="4"
          description="Sesiones en operación"
          icon={BatteryCharging}
          color="#3b82f6"
        />

        <StatCard
          title="Saldo disponible"
          value="$250.00"
          description="Billetera digital"
          icon={Wallet}
          color="#a78bfa"
        />

        <StatCard
          title="Transacciones"
          value="28"
          description="Registro de operaciones SAGA"
          icon={ArrowLeftRight}
          color="#fbbf24"
        />

      </section>

      {/* Gráficas */}
      <section className="grid grid-cols-1 gap-5 xl:grid-cols-3">

        <div className="rounded-xl border border-[#263449] bg-[#152135] p-6 xl:col-span-2">
          <h2 className="text-lg font-semibold">
            Actividad de carga
          </h2>
          <p className="mb-6 mt-1 text-sm text-slate-400">
            Consumo energético durante el día
          </p>

          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={activityData}>
                <defs>
                  <linearGradient
                    id="energyGradient"
                    x1="0"
                    y1="0"
                    x2="0"
                    y2="1"
                  >
                    <stop
                      offset="0%"
                      stopColor="#34d399"
                      stopOpacity={0.35}
                    />
                    <stop
                      offset="100%"
                      stopColor="#34d399"
                      stopOpacity={0}
                    />
                  </linearGradient>
                </defs>

                <CartesianGrid
                  stroke="#263449"
                  strokeDasharray="4 4"
                  vertical={false}
                />

                <XAxis
                  dataKey="hour"
                  stroke="#94a3b8"
                  fontSize={12}
                  tickLine={false}
                />

                <YAxis
                  stroke="#94a3b8"
                  fontSize={12}
                  tickLine={false}
                  unit=" kWh"
                  width={70}
                />

                <Tooltip
                  contentStyle={{
                    backgroundColor: '#111b2d',
                    border: '1px solid #263449',
                    borderRadius: '8px',
                  }}
                  labelStyle={{ color: '#f1f5f9' }}
                />

                <Area
                  type="monotone"
                  dataKey="energy"
                  name="Energía (kWh)"
                  stroke="#34d399"
                  strokeWidth={3}
                  fill="url(#energyGradient)"
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="rounded-xl border border-[#263449] bg-[#152135] p-6">
          <h2 className="text-lg font-semibold">
            Estado de conectores
          </h2>
          <p className="mt-1 text-sm text-slate-400">
            Disponibilidad de infraestructura
          </p>

          <div className="relative mt-6 h-72">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={connectorData}
                  dataKey="value"
                  nameKey="name"
                  innerRadius="58%"
                  outerRadius="82%"
                  paddingAngle={5}
                  stroke="none"
                >
                  {connectorData.map((entry) => (
                    <Cell
                      key={entry.name}
                      fill={entry.color}
                    />
                  ))}
                </Pie>

                <Tooltip />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </div>

      </section>

      {/* Tabla de transacciones */}
      <section className="rounded-xl border border-[#263449] bg-[#152135]">

        <div className="flex items-center justify-between p-6">
          <div>
            <h2 className="text-lg font-semibold">
              Transacciones SAGA recientes
            </h2>
            <p className="mt-1 text-sm text-slate-400">
              Seguimiento de operaciones distribuidas
            </p>
          </div>

          <Link
            to="/transacciones"
            className="text-sm text-emerald-400 hover:text-emerald-300"
          >
            Ver todas
          </Link>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="border-y border-[#263449] bg-[#111b2d] text-slate-400">
              <tr>
                <th className="px-6 py-4">Transacción</th>
                <th className="px-6 py-4">Conector</th>
                <th className="px-6 py-4">Estado</th>
                <th className="px-6 py-4">Monto</th>
              </tr>
            </thead>

            <tbody>
              {transactions.map((transaction) => (
                <tr
                  key={transaction.id}
                  className="border-b border-[#263449] last:border-0 hover:bg-slate-800/30"
                >
                  <td className="px-6 py-5 font-medium">
                    {transaction.id}
                  </td>

                  <td className="px-6 py-5 text-slate-400">
                    {transaction.connector}
                  </td>

                  <td className="px-6 py-5">
                    <span
                      className={`rounded-full px-3 py-1 text-xs font-semibold ${
                        transaction.status === 'SUCCEEDED'
                          ? 'bg-emerald-400/10 text-emerald-400'
                          : 'bg-amber-400/10 text-amber-400'
                      }`}
                    >
                      {transaction.status}
                    </span>
                  </td>

                  <td className="px-6 py-5">
                    ${transaction.amount.toFixed(2)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

      </section>

      <footer className="text-center text-xs text-slate-500">
        AegisVolt — EV Charging Management Platform
      </footer>

    </div>
  )
}

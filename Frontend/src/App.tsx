
import {
  BrowserRouter,
  Routes,
  Route,
} from 'react-router-dom'
import Sesiones from './pages/Sesiones'
import MainLayout from './layouts/MainLayout'
import { RealDashboard, Billetera, Transacciones, Observabilidad } from './pages/Modules'
import Estaciones from './pages/Estaciones'


export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<MainLayout />}>

          <Route index element={<RealDashboard />} />

          <Route
            path="estaciones"
            element={<Estaciones />}
          />

          <Route
            path="sesiones"
            element={<Sesiones />}
          />

          <Route
            path="billetera"
            element={<Billetera />}
          />

          <Route
            path="transacciones"
            element={<Transacciones />}
          />

          <Route
            path="observabilidad"
            element={<Observabilidad />}
          />

        </Route>
      </Routes>
    </BrowserRouter>
  )
}

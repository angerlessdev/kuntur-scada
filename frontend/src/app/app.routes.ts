import { Routes } from '@angular/router';

import { signedIn } from './core/auth';

export const routes: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'flota' },
  {
    path: 'ingresar',
    title: 'Ingresar | Kuntur SCADA',
    loadComponent: () => import('./features/login/login.page').then((m) => m.LoginPage),
  },
  {
    path: 'flota',
    title: 'Flota | Kuntur SCADA',
    canActivate: [signedIn],
    loadComponent: () => import('./features/fleet/fleet.page').then((m) => m.FleetPage),
  },
  {
    path: 'equipos/:id',
    title: 'Equipo | Kuntur SCADA',
    canActivate: [signedIn],
    loadComponent: () => import('./features/device/device.page').then((m) => m.DevicePage),
  },
  {
    path: 'alertas',
    title: 'Alertas | Kuntur SCADA',
    canActivate: [signedIn],
    loadComponent: () => import('./features/alerts/alerts.page').then((m) => m.AlertsPage),
  },
  {
    path: 'auditoria',
    title: 'Auditoría | Kuntur SCADA',
    canActivate: [signedIn],
    loadComponent: () => import('./features/audit/audit.page').then((m) => m.AuditPage),
  },
  { path: '**', redirectTo: 'flota' },
];

import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { catchError, throwError } from 'rxjs';

import { SessionStore } from './session';

/** Adds the session token to API calls and sends the user back to sign in when it stops working. */
export const authInterceptor: HttpInterceptorFn = (request, next) => {
  const session = inject(SessionStore);
  const router = inject(Router);
  const token = session.token();
  const signingIn = request.url.endsWith('/auth/token');
  const authorized =
    token && request.url.startsWith('/api/') && !signingIn
      ? request.clone({ setHeaders: { Authorization: `Bearer ${token}` } })
      : request;
  return next(authorized).pipe(
    catchError((error: unknown) => {
      if (error instanceof HttpErrorResponse && error.status === 401 && !signingIn) {
        session.end();
        void router.navigate(['/ingresar']);
      }
      return throwError(() => error);
    }),
  );
};

export const signedIn: CanActivateFn = () => {
  const session = inject(SessionStore);
  return session.token() ? true : inject(Router).createUrlTree(['/ingresar']);
};

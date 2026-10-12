import datetime
from typing import Optional, List
import bcrypt
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.user import User

ALGORITHM = "HS256"
SECRET_KEY = settings.SECRET_KEY
ACCESS_TOKEN_EXPIRE_MINUTES = settings.ACCESS_TOKEN_EXPIRE_MINUTES

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifica si una contraseña en texto plano coincide con su hash."""
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        return False


def get_password_hash(password: str) -> str:
    """Genera el hash bcrypt para una contraseña dada."""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def is_password_already_in_use(plain_password: str, db: Session, exclude_user_id: Optional[int] = None) -> bool:
    """Verifica si la contraseña ingresada ya está siendo utilizada por algún usuario registrado en el sistema."""
    if not plain_password:
        return False
    query = db.query(User.id, User.hashed_password)
    if exclude_user_id:
        query = query.filter(User.id != exclude_user_id)
    existing_users = query.all()
    for _, hashed_pw in existing_users:
        if hashed_pw and verify_password(plain_password, hashed_pw):
            return True
    return False


def create_access_token(data: dict, expires_delta: Optional[datetime.timedelta] = None) -> str:
    """Genera un token JWT firmado con expiración configurada."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.datetime.utcnow() + expires_delta
    else:
        expire = datetime.datetime.utcnow() + datetime.timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def authenticate_user(db: Session, username: str, password: str) -> Optional[User]:
    """Autentica a un usuario verificando sus credenciales institucionales (correo o usuario)."""
    clean_id = username.strip()
    user = db.query(User).filter(
        (User.email == clean_id.lower()) | (User.username == clean_id)
    ).first()
    if not user:
        return None
    # El perfil Validador solo puede ingresar obligatoriamente mediante su correo electrónico institucional
    if user.role == "Validador" and clean_id.lower() != user.email.lower():
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


def get_token_from_request(request: Request, bearer_token: Optional[str] = Depends(oauth2_scheme)) -> Optional[str]:
    """Extrae el token JWT tanto desde el encabezado Authorization como desde las Cookies."""
    if bearer_token:
        return bearer_token
    cookie_token = request.cookies.get("access_token")
    if cookie_token:
        if cookie_token.startswith("Bearer "):
            return cookie_token[7:]
        return cookie_token
    return None


def get_current_user(
    request: Request,
    token: Optional[str] = Depends(get_token_from_request),
    db: Session = Depends(get_db)
) -> User:
    """
    Dependencia de FastAPI para obtener el usuario autenticado actual.
    Lanza HTTP 401 si no está autenticado o el token es inválido.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciales de autenticación no válidas.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise credentials_exception
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        sub: str = payload.get("sub")
        if sub is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.query(User).filter(
        (User.email == sub.lower()) | (User.username == sub)
    ).first()
    if user is None:
        raise credentials_exception
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Esta cuenta está desactivada."
        )
    return user


def get_current_user_optional(
    request: Request,
    token: Optional[str] = Depends(get_token_from_request),
    db: Session = Depends(get_db)
) -> Optional[User]:
    """Dependencia que retorna el usuario actual si existe y es válido, o None si no hay sesión."""
    if not token:
        return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        sub: str = payload.get("sub")
        if not sub:
            return None
        user = db.query(User).filter(
            (User.email == sub.lower()) | (User.username == sub)
        ).first()
        if user and user.is_active:
            return user
    except Exception:
        return None
    return None


class RoleChecker:
    """Validador de control de acceso basado en roles (RBAC)."""
    def __init__(self, allowed_roles: List[str]):
        self.allowed_roles = allowed_roles

    def __call__(self, current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in self.allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permiso denegado. Se requiere uno de los siguientes roles: {', '.join(self.allowed_roles)}"
            )
        return current_user

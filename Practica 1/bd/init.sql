CREATE TABLE IF NOT EXISTS pacientes (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(255) NOT NULL,
    edad INTEGER NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS citas (
    id SERIAL PRIMARY KEY,
    paciente_id INT REFERENCES pacientes(id),
    fecha DATE NOT NULL,
    hora TIME NOT NULL,
    motivo TEXT
);

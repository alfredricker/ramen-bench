INSERT INTO users (email, name) VALUES
    ('admin@larder.example', 'Larder Admin'),
    ('demo@larder.example', 'Demo Customer'),
    ('support@larder.example', 'Support Desk');

INSERT INTO orders (user_id, total_cents) VALUES
    (2, 5998),
    (2, 3499);

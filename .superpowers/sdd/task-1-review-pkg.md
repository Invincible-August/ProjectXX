# Review package Task 1 (no git)

## Files
- backend/app/core/config.py (Settings fields 62-91)
- backend/.env.example (lines 24-42)

## config.py excerpt
See full file; added fields: super_password, id_verify_mode, id_card_hash_salt, sms_provider, email_provider, id_two_factor_provider, id_real_person_provider, verify_code_ttl_seconds, verify_ticket_ttl_seconds, verify_send_interval_seconds, debug_verify_code

## .env.example note
ID_VERIFY_MODE comment currently says: format（仅格式）| hash（哈希比对）| provider（外部实人）
Plan/spec require: format | two_factor | real_person

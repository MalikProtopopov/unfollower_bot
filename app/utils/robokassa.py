"""Robokassa payment integration utilities."""

import hashlib
from decimal import Decimal
from urllib.parse import urlencode

from app.utils.logger import logger


def generate_payment_url(
    merchant_login: str,
    password_1: str,
    inv_id: str,
    out_sum: Decimal,
    description: str,
    user_id: int,
    tariff_id: str,
    test_mode: bool = True,
) -> str:
    """Generate Robokassa payment URL with proper signature.
    
    Args:
        merchant_login: Shop identifier in Robokassa
        password_1: Password #1 for signature generation
        inv_id: Invoice/payment ID (will be used as InvId)
        out_sum: Payment amount in RUB
        description: Payment description
        user_id: Telegram user ID (will be passed as Shp_user_id)
        tariff_id: Tariff ID (will be passed as Shp_tariff_id)
        test_mode: Whether to use test mode
        
    Returns:
        Full URL for redirecting user to Robokassa payment page
    """
    # Format amount with 2 decimal places (required by Robokassa)
    out_sum_str = f"{out_sum:.2f}"
    
    # Build signature string: MerchantLogin:OutSum:InvId:Password1:Shp_*
    # Shp_* parameters must be in alphabetical order
    shp_params = {
        "Shp_payment_id": inv_id,
        "Shp_tariff_id": tariff_id,
        "Shp_user_id": str(user_id),
    }
    shp_str = ":".join(f"{k}={v}" for k, v in sorted(shp_params.items()))
    
    signature_str = f"{merchant_login}:{out_sum_str}:{inv_id}:{password_1}:{shp_str}"
    signature = hashlib.md5(signature_str.encode()).hexdigest().upper()
    
    logger.debug(f"Robokassa signature string: {signature_str}")
    logger.debug(f"Robokassa signature: {signature}")
    
    # Build URL parameters
    params = {
        "MerchantLogin": merchant_login,
        "OutSum": out_sum_str,
        "InvId": inv_id,
        "Description": description,
        "SignatureValue": signature,
        "Culture": "ru",
        "Encoding": "utf-8",
        **shp_params,
    }
    
    if test_mode:
        params["IsTest"] = "1"
    
    base_url = "https://auth.robokassa.ru/Merchant/Index.aspx"
    url = f"{base_url}?{urlencode(params)}"
    
    logger.info(f"Generated Robokassa payment URL for InvId={inv_id}, amount={out_sum_str}")
    
    return url


def verify_callback_signature(
    out_sum: str,
    inv_id: str,
    signature: str,
    password_2: str,
    shp_params: dict[str, str],
) -> bool:
    """Verify Robokassa callback signature.
    
    Args:
        out_sum: Payment amount from callback
        inv_id: Invoice ID from callback
        signature: SignatureValue from callback
        password_2: Password #2 for signature verification
        shp_params: Dictionary of Shp_* parameters from callback
        
    Returns:
        True if signature is valid, False otherwise
    """
    # Build signature string: OutSum:InvId:Password2:Shp_*
    # Shp_* parameters must be in alphabetical order (same as in URL generation)
    shp_str = ":".join(f"{k}={v}" for k, v in sorted(shp_params.items()))
    
    signature_str = f"{out_sum}:{inv_id}:{password_2}"
    if shp_str:
        signature_str += f":{shp_str}"
    
    expected_signature = hashlib.md5(signature_str.encode()).hexdigest().upper()
    received_signature = signature.upper()
    
    logger.debug(f"Robokassa callback signature string: {signature_str}")
    logger.debug(f"Expected signature: {expected_signature}")
    logger.debug(f"Received signature: {received_signature}")
    
    is_valid = received_signature == expected_signature
    
    if not is_valid:
        logger.warning(
            f"Invalid Robokassa callback signature for InvId={inv_id}. "
            f"Expected: {expected_signature}, Received: {received_signature}"
        )
    else:
        logger.info(f"Valid Robokassa callback signature for InvId={inv_id}")
    
    return is_valid


def format_callback_response(inv_id: str) -> str:
    """Format successful callback response for Robokassa.
    
    Robokassa expects response in format: OK{InvId}
    
    Args:
        inv_id: Invoice ID
        
    Returns:
        Formatted response string
    """
    return f"OK{inv_id}\n"


def verify_amount(expected_amount: Decimal, received_amount: str) -> bool:
    """Verify that callback amount matches expected payment amount.
    
    Args:
        expected_amount: Expected amount from database
        received_amount: Amount received in callback
        
    Returns:
        True if amounts match, False otherwise
    """
    try:
        received = Decimal(received_amount)
        # Compare with 2 decimal precision
        is_valid = abs(expected_amount - received) < Decimal("0.01")
        
        if not is_valid:
            logger.warning(
                f"Amount mismatch: expected={expected_amount}, received={received_amount}"
            )
        
        return is_valid
    except Exception as e:
        logger.error(f"Error verifying amount: {e}")
        return False


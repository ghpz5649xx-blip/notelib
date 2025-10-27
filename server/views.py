# app/views.py
import os
import base64
import hashlib
import cloudpickle
import logging
from django.conf import settings
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import AllowAny 
from rest_framework import status
from pathlib import Path
import traceback


from .models import FeatureMeta
from notelib_core.loader import load_notebook_features
from .services import feature_service

logger = logging.getLogger("notelib")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("[NoteLib] %(levelname)s: %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
logger.setLevel(logging.INFO)



# =======================================================
# 📥 Import de features sérialisées
# =======================================================
@api_view(["POST"])
def import_feature(request):
    """
    Réceptionne une feature sérialisée (base64 pickle) depuis le client sandbox.
    """
    try:
        name = request.data.get("name")
        hash_ = request.data.get("hash")
        inputs = request.data.get("inputs", [])
        outputs = request.data.get("outputs", [])
        obj_data_b64 = request.data.get("obj_data")

        if not all([name, hash_, obj_data_b64]):
            return Response({"error": "Missing required fields."}, status=status.HTTP_400_BAD_REQUEST)

        # Vérification d’intégrité
        obj_bytes = base64.b64decode(obj_data_b64)
        computed_hash = hashlib.sha256(obj_bytes).hexdigest()
        if computed_hash != hash_:
            return Response({"error": "Hash mismatch."}, status=status.HTTP_400_BAD_REQUEST)

        base_dir = getattr(settings, "FEATURE_DATA_DIR", os.path.join(settings.BASE_DIR, "data", "features"))
        os.makedirs(base_dir, exist_ok=True)
        file_path = os.path.join(base_dir, f"{name}_{hash_}.pkl")

        # Écriture du binaire
        with open(file_path, "wb") as f:
            f.write(obj_bytes)
        logger.info(f"📦 Feature binary saved: {file_path}")

        feature, created = FeatureMeta.objects.get_or_create(
            name=name,
            hash=hash_,
            defaults={"input_types": inputs, "output_types": outputs},
        )

        # Chargement du binaire
        try:
            with open(file_path, "rb") as f:
                obj = cloudpickle.load(f)
            feature_service.registry.register(obj)
            logger.info(f"✅ Feature '{name}' loaded in memory.")
        except Exception as e:
            logger.warning(f"⚠️ Could not unpickle feature {name}: {e}")
            return Response({"error": "Failed to load pickle."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response(
            {
                "status": "success",
                "created": created,
                "name": name,
                "hash": hash_,
                "path": file_path,
            },
            status=status.HTTP_200_OK,
        )

    except Exception as e:
        logger.error(f"Error in import_feature: {e}")
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# =======================================================
# 📜 Liste des features
# =======================================================
@api_view(["GET"])
def list_features(request):
    try:
        features = FeatureMeta.objects.all().order_by("-created_at")
        data = [
            {
                "name": f.name,
                "hash": f.hash,
                "inputs": f.inputs,
                "outputs": f.outputs,
                "created_at": f.created_at.isoformat(),
            }
            for f in features
        ]
        return Response({"count": len(data), "features": data}, status=status.HTTP_200_OK)
    except Exception as e:
        logger.error(f"Error listing features: {e}")
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["POST"])
def exec(request):
    try:
        feature_name = request.data.get("name")
        feature_hash = FeatureMeta.objects.filter(name=feature_name).order_by("-created_at").first().hash
        feature = feature_service.load_feature(hash_value=feature_hash)
        output = feature()
        return Response({"output": output}, status=status.HTTP_200_OK)
    except Exception as e:
        t = traceback.format_exc() 
        logger.error(f"Error exec features: {e} Trace : {t}")
        return Response(f"Error exec features: {e} Trace : {t}", status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# =======================================================
# 📘 Chargement de notebook
# =======================================================
@api_view(["POST"])
def load_notebook(request):
    """
    POST /api/features/load_notebook/
    {
        "path": "/path/to/notebook.ipynb",
        "sandbox_mode": "temp",
        "publish": true
    }
    """
    try:
        notebook_path = request.data.get("path")
        sandbox_mode = request.data.get("sandbox_mode", "temp")
        publish = bool(request.data.get("publish", True))

        if not notebook_path:
            return Response({"error": "Missing 'path' field."}, status=status.HTTP_400_BAD_REQUEST)

        path_obj = Path(notebook_path)
        if not path_obj.exists():
            return Response({"error": f"Notebook not found: {notebook_path}"}, status=status.HTTP_404_NOT_FOUND)

        result = load_notebook_features(path_obj, sandbox_mode=sandbox_mode, publish=publish)

        features_data = [
            {
                "name": f.name,
                "hash": f.hash,
                "inputs": f.inputs,
                "outputs": f.outputs,
                "code": f.code,
                "defined_in": getattr(f, "defined_in", str(path_obj)),
            }
            for f in result.get("features", [])
        ]

        return Response(
            {
                "status": "success",
                "features_loaded": len(features_data),
                "errors_count": len(result["errors"]),
                "errors": result["errors"],
                "features": features_data,
            },
            status=status.HTTP_200_OK,
        )

    except SyntaxError as e:
        return Response({"error": "SyntaxError", "details": str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        logger.error(f"Unexpected error in load_notebook: {e}")
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# =======================================================
# 📥 Import de features depuis le client
# =======================================================
@api_view(["POST"])
@permission_classes([AllowAny])  # TODO: Ajouter authentification
def import_feature(request):
    """
    Reçoit une feature sérialisée depuis un client notelib_core.
    
    POST /api/features/import/
    {
        "name": "load",
        "hash": "e3b0c442...",
        "code": "@feature\ndef load(path):\n    ...",
        "inputs": ["path"],
        "outputs": ["load"],
        "defined_in": "/path/to/notebook.ipynb",
        "obj_data": "base64_encoded_pickle"
    }
    
    Returns:
        {
            "status": "success",
            "created": true,
            "feature": {
                "name": "load",
                "hash": "e3b0c442...",
                "binary_path": "by_hash/e3/e3b0c442...pkl"
            }
        }
    """
    try:
        # Extraction des données
        name = request.data.get("name")
        hash_value = request.data.get("hash")
        code = request.data.get("code", "")
        inputs = request.data.get("inputs", [])
        outputs = request.data.get("outputs", [])
        defined_in = request.data.get("defined_in")
        obj_data_b64 = request.data.get("obj_data")
        
        # Validation
        if not all([name, hash_value, obj_data_b64]):
            return Response(
                {"error": "Missing required fields: name, hash, obj_data"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Décodage du binaire
        try:
            obj_bytes = base64.b64decode(obj_data_b64)
        except Exception as e:
            return Response(
                {"error": f"Invalid base64 encoding: {e}"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Vérification d'intégrité (hash du binaire)
        computed_hash = hashlib.sha256(obj_bytes).hexdigest()
        logger.debug(f"Binary hash: {computed_hash}, Code hash: {hash_value}")
        
        # Note: Le hash peut être différent car il est calculé sur le code source,
        # pas sur le binaire pickle. On log juste pour info.
        
        # Désérialisation de l'objet
        try:
            obj = cloudpickle.loads(obj_bytes)
        except Exception as e:
            return Response(
                {"error": f"Failed to unpickle object: {e}"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Préparation des données pour le service
        feature_data = {
            'name': name,
            'hash': hash_value,
            'code': code,
            'inputs': inputs,
            'outputs': outputs,
            'obj': obj,
            'defined_in': defined_in,
        }
        
        # Import via le service
        feature, created = feature_service.import_feature(feature_data)
        
        return Response({
            "status": "success",
            "created": created,
            "feature": {
                "name": feature.name,
                "hash": feature.hash,
                "created_at": feature.created_at.isoformat(),
            }
        }, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"Error importing feature: {e}", exc_info=True)
        return Response(
            {"error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


package auth

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"strconv"
	"strings"

	"golang.org/x/crypto/pbkdf2"
)

func VerifyPassword(password string, encoded string) bool {
	parts := strings.SplitN(encoded, "$", 4)
	if len(parts) != 4 {
		return false
	}
	if parts[0] != "pbkdf2_sha256" {
		return false
	}
	iterations, err := strconv.Atoi(parts[1])
	if err != nil {
		return false
	}
	salt, err := base64.URLEncoding.DecodeString(parts[2])
	if err != nil {
		salt, err = base64.RawURLEncoding.DecodeString(parts[2])
		if err != nil {
			return false
		}
	}
	expectedDigest, err := base64.URLEncoding.DecodeString(parts[3])
	if err != nil {
		expectedDigest, err = base64.RawURLEncoding.DecodeString(parts[3])
		if err != nil {
			return false
		}
	}
	actualDigest := pbkdf2.Key([]byte(password), salt, iterations, len(expectedDigest), sha256.New)
	return hmac.Equal(actualDigest, expectedDigest)
}
